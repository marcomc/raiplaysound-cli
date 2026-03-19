from __future__ import annotations

import contextlib
import dataclasses
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from rich.progress import Progress, TaskID


@dataclasses.dataclass(slots=True)
class DownloadTask:
    episode_id: str
    episode_url: str
    episode_label: str
    task_id: TaskID


@dataclasses.dataclass(slots=True)
class PreparedDownload:
    episode_id: str
    episode_label: str
    work_dir: Path
    media_path: Path
    final_path: Path
    info_json_path: Path | None
    thumbnail_path: Path | None
    duration_seconds: float


class Downloader:
    def __init__(
        self,
        *,
        archive_file: Path,
        output_template: str,
        work_root: Path,
        audio_format: str,
        log_file: Path | None,
        rich_progress: Progress,
        debug_pids: bool,
        overall_task_id: TaskID | None = None,
    ) -> None:
        self.archive_file = archive_file
        self.output_template = output_template
        self.work_root = work_root
        self.audio_format = audio_format
        self.log_file = log_file
        self.progress = rich_progress
        self.debug_pids = debug_pids
        self.overall_task_id = overall_task_id
        self.lock = threading.Lock()
        self.processes: set[subprocess.Popen[str]] = set()
        self.task_samples: dict[TaskID, tuple[float, int]] = {}
        self.task_rates: dict[TaskID, float] = {}

    def log(self, message: str) -> None:
        if self.log_file is not None:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    def terminate_all(self) -> None:
        with self.lock:
            for process in list(self.processes):
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()

    def _update_overall_speed(self, task_id: TaskID, downloaded_bytes: int) -> None:
        if self.overall_task_id is None:
            return
        now = time.monotonic()
        with self.lock:
            previous = self.task_samples.get(task_id)
            if previous is not None:
                previous_time, previous_bytes = previous
                elapsed = now - previous_time
                delta = downloaded_bytes - previous_bytes
                if elapsed > 0 and delta > 0:
                    self.task_rates[task_id] = delta / elapsed
            self.task_samples[task_id] = (now, downloaded_bytes)
            speed_text = _format_transfer_speed(sum(self.task_rates.values()))
        self.progress.update(self.overall_task_id, speed_text=speed_text)

    def _clear_overall_speed(self, task_id: TaskID) -> None:
        if self.overall_task_id is None:
            return
        with self.lock:
            self.task_samples.pop(task_id, None)
            self.task_rates.pop(task_id, None)
            speed_text = _format_transfer_speed(sum(self.task_rates.values()))
        self.progress.update(self.overall_task_id, speed_text=speed_text)

    def _spawn(self, cmd: list[str]) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        with self.lock:
            self.processes.add(process)
        return process

    def _finalize_process(self, process: subprocess.Popen[str]) -> int:
        process.wait()
        with self.lock:
            self.processes.discard(process)
        return process.returncode

    def download_source(self, task: DownloadTask) -> tuple[str, str, PreparedDownload | None]:
        parse_metadata_expr = (
            r"title:^(?P<series>.+?) "
            r"S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$"
        )
        work_dir = self.work_root / task.episode_id
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "yt-dlp",
            "--format",
            "bestaudio/best",
            "--parse-metadata",
            parse_metadata_expr,
            "--no-overwrites",
            "--ignore-errors",
            "--write-info-json",
            "--write-thumbnail",
            "--newline",
            "--progress",
            "--progress-template",
            "progress:%(progress.downloaded_bytes|0)d:%(progress.total_bytes|0)d:%(progress.total_bytes_estimate|0)d:%(progress._percent_str)s",
            "--print",
            "after_move:filepath",
            "-o",
            str(work_dir / Path(self.output_template).name),
            task.episode_url,
        ]
        if self.log_file is not None:
            cmd.insert(-2, "--verbose")
        process = self._spawn(cmd)
        if self.debug_pids:
            self.log(f"[pid] episode={task.episode_id} pid={process.pid}")
        state = "DONE"
        detail = "done"
        output_path: Path | None = None
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if self.log_file is not None and not line.startswith("progress:"):
                self.log(line)
            if line.startswith("ERROR:"):
                state = "ERROR"
                detail = "error"
                self.progress.update(
                    task.task_id,
                    description=f"error {task.episode_label}",
                    completed=100,
                    total=100,
                    size_text="",
                    speed_text="",
                )
                self._clear_overall_speed(task.task_id)
                continue
            if not line.startswith("progress:"):
                candidate = Path(line.strip())
                if candidate.is_absolute():
                    output_path = candidate
                continue
            _, downloaded_s, total_s, estimate_s, raw_percent = line.split(":", 4)
            downloaded = int(downloaded_s) if downloaded_s.isdigit() else 0
            total = int(total_s) if total_s.isdigit() else 0
            estimate = int(estimate_s) if estimate_s.isdigit() else 0
            if total > 0:
                self.progress.update(
                    task.task_id,
                    total=total,
                    completed=downloaded,
                    size_text=_format_megabyte_progress(downloaded, total),
                    speed_text="",
                )
                self._update_overall_speed(task.task_id, downloaded)
            elif estimate > 0:
                self.progress.update(
                    task.task_id,
                    total=estimate,
                    completed=downloaded,
                    size_text=_format_megabyte_progress(downloaded, estimate),
                    speed_text="",
                )
                self._update_overall_speed(task.task_id, downloaded)
            else:
                percent_text = raw_percent.strip().replace("%", "")
                try:
                    percent = min(int(float(percent_text)), 100)
                except ValueError:
                    continue
                self.progress.update(
                    task.task_id,
                    completed=percent,
                    total=100,
                    size_text=_format_megabyte_progress(downloaded, 0),
                    speed_text="",
                )
                self._update_overall_speed(task.task_id, downloaded)
        returncode = self._finalize_process(process)
        if returncode != 0:
            state = "ERROR"
            detail = f"yt-dlp exit code {returncode}"
        self._clear_overall_speed(task.task_id)
        if state == "ERROR" or output_path is None or not output_path.exists():
            self.progress.remove_task(task.task_id)
            shutil.rmtree(work_dir, ignore_errors=True)
            return state, detail if state == "ERROR" else "missing download output", None
        info_json_path = output_path.with_suffix(".info.json")
        thumbnail_path = _find_thumbnail(output_path)
        prepared = PreparedDownload(
            episode_id=task.episode_id,
            episode_label=task.episode_label,
            work_dir=work_dir,
            media_path=output_path,
            final_path=self.archive_file.parent / f"{output_path.stem}.{self.audio_format}",
            info_json_path=info_json_path if info_json_path.exists() else None,
            thumbnail_path=thumbnail_path,
            duration_seconds=(
                _read_duration_seconds(info_json_path) if info_json_path.exists() else 0.0
            ),
        )
        self.progress.update(
            task.task_id,
            description=f"queue {task.episode_label}",
            size_text="queued",
            speed_text="",
        )
        return "READY", "downloaded", prepared

    def convert_one(self, task: DownloadTask, prepared: PreparedDownload) -> tuple[str, str]:
        metadata = _load_sidecar_metadata(prepared.info_json_path, task.episode_label)
        duration_units = max(int(prepared.duration_seconds * 1_000_000), 1)
        self.progress.update(
            task.task_id,
            description=f"convert {task.episode_label}",
            total=duration_units,
            completed=0,
            size_text="converting",
            speed_text="",
        )
        prepared.final_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = _build_ffmpeg_command(
            prepared=prepared,
            audio_format=self.audio_format,
            metadata=metadata,
        )
        process = self._spawn(cmd)
        if self.debug_pids:
            self.log(f"[pid] convert={task.episode_id} pid={process.pid}")
        assert process.stdout is not None
        last_progress = 0
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if self.log_file is not None and line:
                self.log(line)
            if line.startswith("out_time_us="):
                value = line.partition("=")[2]
                if value.isdigit():
                    last_progress = min(int(value), duration_units)
                    self.progress.update(task.task_id, completed=last_progress)
            elif line.startswith("out_time_ms="):
                value = line.partition("=")[2]
                if value.isdigit():
                    out_time_us = int(value) * 1000
                    last_progress = min(out_time_us, duration_units)
                    self.progress.update(task.task_id, completed=last_progress)
        returncode = self._finalize_process(process)
        if returncode != 0:
            self.progress.update(
                task.task_id,
                description=f"error {task.episode_label}",
                size_text="",
                speed_text="",
            )
            self.progress.remove_task(task.task_id)
            shutil.rmtree(prepared.work_dir, ignore_errors=True)
            return "ERROR", f"ffmpeg exit code {returncode}"
        self.progress.update(
            task.task_id,
            completed=duration_units,
            description=f"done {task.episode_label}",
            size_text="",
            speed_text="",
        )
        _append_archive_entry(self.archive_file, prepared.episode_id)
        shutil.rmtree(prepared.work_dir, ignore_errors=True)
        self.progress.remove_task(task.task_id)
        return "DONE", "done"


def _format_megabyte_progress(downloaded_bytes: int, total_bytes: int) -> str:
    downloaded_mb = downloaded_bytes / 1_000_000
    if total_bytes > 0:
        total_mb = total_bytes / 1_000_000
        return f"{downloaded_mb:.1f}/{total_mb:.1f} MB"
    return f"{downloaded_mb:.1f} MB"


def _format_transfer_speed(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return ""
    megabytes_per_second = bytes_per_second / 1_000_000
    if megabytes_per_second >= 1:
        return f"{megabytes_per_second:.1f} MB/s"
    kilobytes_per_second = bytes_per_second / 1_000
    return f"{kilobytes_per_second:.0f} KB/s"


def _find_thumbnail(media_path: Path) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = media_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def _read_duration_seconds(info_json_path: Path) -> float:
    try:
        payload = json.loads(info_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.0
    duration = payload.get("duration")
    if isinstance(duration, (int, float)) and duration > 0:
        return float(duration)
    return 0.0


def _load_sidecar_metadata(info_json_path: Path | None, default_title: str) -> dict[str, str]:
    payload: dict[str, object] = {}
    if info_json_path is not None:
        try:
            raw_payload = json.loads(info_json_path.read_text(encoding="utf-8"))
            if isinstance(raw_payload, dict):
                payload = raw_payload
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            payload = {}
    upload_date = str(payload.get("upload_date") or "").strip()
    date_value = ""
    if len(upload_date) == 8 and upload_date.isdigit():
        date_value = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    episode_title = str(payload.get("episode") or "").strip()
    title = episode_title or str(payload.get("title") or default_title)
    series = str(payload.get("series") or payload.get("playlist_title") or "").strip()
    artist = str(payload.get("uploader") or "").strip()
    season_number = str(payload.get("season_number") or "").strip()
    episode_number = str(payload.get("episode_number") or "").strip()
    metadata = {"title": title}
    if series:
        metadata["album"] = series
    if artist:
        metadata["artist"] = artist
    if date_value:
        metadata["date"] = date_value
    if episode_number.isdigit():
        metadata["track"] = episode_number
    if season_number.isdigit():
        metadata["disc"] = season_number
    return metadata


def _build_ffmpeg_command(
    *, prepared: PreparedDownload, audio_format: str, metadata: dict[str, str]
) -> list[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(prepared.media_path),
    ]
    supports_cover_art = audio_format in {"mp3", "m4a", "aac"}
    if (
        supports_cover_art
        and prepared.thumbnail_path is not None
        and prepared.thumbnail_path.exists()
    ):
        cmd.extend(
            [
                "-i",
                str(prepared.thumbnail_path),
                "-map",
                "0:a",
                "-map",
                "1:v",
                "-c:v",
                "copy",
                "-disposition:v",
                "attached_pic",
            ]
        )
    else:
        cmd.extend(["-map", "0:a"])
    cmd.extend(_ffmpeg_audio_codec_args(audio_format))
    for key, value in metadata.items():
        cmd.extend(["-metadata", f"{key}={value}"])
    cmd.extend(
        [
            "-progress",
            "pipe:1",
            "-nostats",
            str(prepared.final_path),
        ]
    )
    return cmd


def _ffmpeg_audio_codec_args(audio_format: str) -> list[str]:
    if audio_format == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "0"]
    if audio_format == "m4a":
        return ["-c:a", "aac", "-q:a", "0"]
    if audio_format == "aac":
        return ["-c:a", "aac", "-q:a", "0"]
    if audio_format == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "8"]
    if audio_format == "opus":
        return ["-c:a", "libopus", "-b:a", "192k"]
    if audio_format == "flac":
        return ["-c:a", "flac"]
    if audio_format == "wav":
        return ["-c:a", "pcm_s16le"]
    return ["-c:a", "copy"]


def _append_archive_entry(archive_file: Path, episode_id: str) -> None:
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if archive_file.exists():
        existing = set(archive_file.read_text(encoding="utf-8").splitlines())
    line = f"raiplaysound {episode_id}"
    if line in existing:
        return
    with archive_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def resolve_log_file(
    *,
    enable_log: bool,
    debug_pids: bool,
    log_path_arg: str,
    target_dir: Path,
    slug: str,
) -> Path | None:
    if not (enable_log or debug_pids):
        return None
    run_ts = time.strftime("%Y%m%d-%H%M%S")
    raw = log_path_arg
    if not raw:
        path = target_dir / f"{slug}-run-{run_ts}.log"
    else:
        candidate = Path(raw)
        if candidate.exists() and candidate.is_dir():
            path = candidate / f"{slug}-run-{run_ts}.log"
        elif raw.endswith("/"):
            candidate.mkdir(parents=True, exist_ok=True)
            path = candidate / f"{slug}-run-{run_ts}.log"
        else:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            path = candidate
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def remove_missing_ids_from_archive(archive_file: Path, missing_ids: set[str]) -> None:
    if not archive_file.exists():
        return
    kept = []
    for line in archive_file.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and parts[1] in missing_ids:
            continue
        kept.append(line)
    archive_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
