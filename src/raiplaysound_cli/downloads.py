from __future__ import annotations

import contextlib
import dataclasses
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


class Downloader:
    def __init__(
        self,
        *,
        archive_file: Path,
        output_template: str,
        audio_format: str,
        log_file: Path | None,
        rich_progress: Progress,
        debug_pids: bool,
    ) -> None:
        self.archive_file = archive_file
        self.output_template = output_template
        self.audio_format = audio_format
        self.log_file = log_file
        self.progress = rich_progress
        self.debug_pids = debug_pids
        self.lock = threading.Lock()
        self.processes: set[subprocess.Popen[str]] = set()

    def log(self, message: str) -> None:
        if self.log_file is not None:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    def terminate_all(self) -> None:
        with self.lock:
            for process in list(self.processes):
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()

    def download_one(self, task: DownloadTask) -> tuple[str, str]:
        parse_metadata_expr = (
            r"title:^(?P<series>.+?) "
            r"S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$"
        )
        cmd = [
            "yt-dlp",
            "--format",
            "bestaudio/best",
            "--parse-metadata",
            parse_metadata_expr,
            "--download-archive",
            str(self.archive_file),
            "--no-overwrites",
            "--ignore-errors",
            "--extract-audio",
            "--audio-format",
            self.audio_format,
            "--audio-quality",
            "0",
            "--add-metadata",
            "--embed-thumbnail",
            "--newline",
            "--progress",
            "--progress-template",
            "progress:%(progress.downloaded_bytes|0)d:%(progress.total_bytes|0)d:%(progress.total_bytes_estimate|0)d:%(progress._percent_str)s",
            "-o",
            self.output_template,
            task.episode_url,
        ]
        if self.log_file is not None:
            cmd.insert(-2, "--verbose")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        with self.lock:
            self.processes.add(process)
        if self.debug_pids:
            self.log(f"[pid] episode={task.episode_id} pid={process.pid}")
        state = "DONE"
        detail = "done"
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if self.log_file is not None and not line.startswith("progress:"):
                self.log(line)
            if "has already been recorded in the archive" in line:
                state = "SKIP"
                detail = "downloaded"
                self.progress.update(
                    task.task_id,
                    description=f"skip {task.episode_label}",
                    completed=100,
                    total=100,
                )
                continue
            if line.startswith("ERROR:"):
                state = "ERROR"
                detail = "error"
                self.progress.update(
                    task.task_id,
                    description=f"error {task.episode_label}",
                    completed=100,
                    total=100,
                )
                continue
            if not line.startswith("progress:"):
                continue
            _, downloaded_s, total_s, estimate_s, raw_percent = line.split(":", 4)
            downloaded = int(downloaded_s) if downloaded_s.isdigit() else 0
            total = int(total_s) if total_s.isdigit() else 0
            estimate = int(estimate_s) if estimate_s.isdigit() else 0
            if total > 0:
                self.progress.update(task.task_id, total=total, completed=downloaded)
            elif estimate > 0:
                self.progress.update(task.task_id, total=estimate, completed=downloaded)
            else:
                percent_text = raw_percent.strip().replace("%", "")
                try:
                    percent = min(int(float(percent_text)), 100)
                except ValueError:
                    continue
                self.progress.update(task.task_id, completed=percent, total=100)
        process.wait()
        with self.lock:
            self.processes.discard(process)
        if process.returncode != 0 and state != "SKIP":
            state = "ERROR"
            detail = f"yt-dlp exit code {process.returncode}"
        self.progress.remove_task(task.task_id)
        return state, detail


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
