from __future__ import annotations

from pathlib import Path
from typing import cast

from rich.progress import TaskID

from raiplaysound_cli.downloads import (
    Downloader,
    DownloadTask,
    PreparedDownload,
    _build_ffmpeg_command,
    _load_sidecar_metadata,
)


class RecordingProgress:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []
        self.removed: list[int] = []

    def update(self, task_id: int, **kwargs: object) -> None:
        self.updated.append({"task_id": task_id, **kwargs})

    def remove_task(self, task_id: int) -> None:
        self.removed.append(task_id)


class FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode
        self.pid = 12345

    def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15


def test_downloader_parses_progress_lines(monkeypatch, tmp_path: Path) -> None:
    progress = RecordingProgress()
    task = DownloadTask(
        episode_id="ep-1",
        episode_url="https://example.test/ep-1",
        episode_label="Episode 1",
        task_id=cast(TaskID, 7),
    )
    work_file = tmp_path / "work" / "ep-1" / "Episode 1.mp3"
    work_file.parent.mkdir(parents=True)
    work_file.write_bytes(b"audio")
    fake_process = FakeProcess(
        [
            "progress:10:100:0:10.0%",
            "progress:40:100:0:40.0%",
            "progress:100:100:0:100.0%",
            str(work_file),
        ]
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr("raiplaysound_cli.downloads.shutil.rmtree", lambda *_args, **_kwargs: None)

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        work_root=tmp_path / "work",
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
    )

    state, detail, prepared = downloader.download_source(task)

    assert (state, detail) == ("READY", "downloaded")
    assert prepared is not None
    assert prepared.media_path == work_file
    assert progress.removed == []
    assert {
        "task_id": 7,
        "total": 100,
        "completed": 10,
        "size_text": "0.0/0.0 MB",
        "speed_text": "",
    } in progress.updated
    assert {
        "task_id": 7,
        "total": 100,
        "completed": 40,
        "size_text": "0.0/0.0 MB",
        "speed_text": "",
    } in progress.updated
    assert {
        "task_id": 7,
        "total": 100,
        "completed": 100,
        "size_text": "0.0/0.0 MB",
        "speed_text": "",
    } in progress.updated
    assert {
        "task_id": 7,
        "description": "queue Episode 1",
        "size_text": "queued",
        "speed_text": "",
    } in progress.updated


def test_downloader_formats_megabytes_and_updates_overall_speed(
    monkeypatch, tmp_path: Path
) -> None:
    progress = RecordingProgress()
    task = DownloadTask(
        episode_id="ep-1",
        episode_url="https://example.test/ep-1",
        episode_label="Episode 1",
        task_id=cast(TaskID, 8),
    )
    work_file = tmp_path / "work" / "ep-1" / "Episode 1.mp3"
    work_file.parent.mkdir(parents=True)
    work_file.write_bytes(b"audio")
    fake_process = FakeProcess(
        [
            "progress:5000000:10000000:0:50.0%",
            "progress:10000000:10000000:0:100.0%",
            str(work_file),
        ]
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    monkeypatch.setattr("raiplaysound_cli.downloads.shutil.rmtree", lambda *_args, **_kwargs: None)
    times = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr("raiplaysound_cli.downloads.time.monotonic", lambda: next(times))

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        work_root=tmp_path / "work",
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
        overall_task_id=cast(TaskID, 99),
    )

    state, detail, _prepared = downloader.download_source(task)

    assert (state, detail) == ("READY", "downloaded")
    assert {
        "task_id": 8,
        "total": 10000000,
        "completed": 5000000,
        "size_text": "5.0/10.0 MB",
        "speed_text": "",
    } in progress.updated
    assert {
        "task_id": 8,
        "total": 10000000,
        "completed": 10000000,
        "size_text": "10.0/10.0 MB",
        "speed_text": "",
    } in progress.updated
    assert {"task_id": 99, "speed_text": "5.0 MB/s"} in progress.updated
    assert {"task_id": 99, "speed_text": ""} in progress.updated


def test_downloader_reports_source_errors(monkeypatch, tmp_path: Path) -> None:
    progress = RecordingProgress()
    task = DownloadTask(
        episode_id="ep-2",
        episode_url="https://example.test/ep-2",
        episode_label="Episode 2",
        task_id=cast(TaskID, 9),
    )
    fake_process = FakeProcess(["ERROR: failed"], returncode=1)
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        work_root=tmp_path / "work",
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
    )

    state, detail, prepared = downloader.download_source(task)

    assert (state, detail) == ("ERROR", "yt-dlp exit code 1")
    assert prepared is None
    assert progress.updated[-1]["description"] == "error Episode 2"
    assert progress.removed == [9]


def test_downloader_converts_and_appends_archive(monkeypatch, tmp_path: Path) -> None:
    progress = RecordingProgress()
    task = DownloadTask(
        episode_id="ep-3",
        episode_url="https://example.test/ep-3",
        episode_label="Episode 3",
        task_id=cast(TaskID, 10),
    )
    work_dir = tmp_path / "work" / "ep-3"
    work_dir.mkdir(parents=True)
    media_path = work_dir / "Episode 3.mp3"
    media_path.write_bytes(b"audio")
    info_json = media_path.with_suffix(".info.json")
    info_json.write_text(
        '{"title": "Episode 3", "upload_date": "20260319", "series": "Battiti", "duration": 2}',
        encoding="utf-8",
    )
    final_path = tmp_path / "Episode 3.m4a"
    fake_process = FakeProcess(["out_time_us=1000000", "out_time_us=2000000"])
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        work_root=tmp_path / "work",
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads._build_ffmpeg_command",
        lambda **kwargs: ["ffmpeg", "-y", str(media_path), str(final_path)],
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.shutil.rmtree",
        lambda *_args, **_kwargs: None,
    )
    final_path.write_bytes(b"converted")
    prepared = PreparedDownload(
        episode_id="ep-3",
        episode_label="Episode 3",
        work_dir=work_dir,
        media_path=media_path,
        final_path=final_path,
        info_json_path=info_json,
        thumbnail_path=None,
        duration_seconds=2.0,
    )

    state, detail = downloader.convert_one(task, prepared)

    assert (state, detail) == ("DONE", "done")
    assert progress.removed == [10]
    assert (tmp_path / ".download-archive.txt").read_text(encoding="utf-8") == "raiplaysound ep-3\n"


def test_sidecar_metadata_restores_season_and_episode_tags(tmp_path: Path) -> None:
    info_json = tmp_path / "episode.info.json"
    info_json.write_text(
        (
            '{"title": "America7 S2E16 L\'azzardo di Trump", '
            '"episode": "L\'azzardo di Trump", '
            '"series": "America7", '
            '"uploader": "raiplay sound", '
            '"upload_date": "20260306", '
            '"season_number": "2", '
            '"episode_number": "16"}'
        ),
        encoding="utf-8",
    )
    metadata = _load_sidecar_metadata(info_json, "fallback")

    assert metadata == {
        "title": "L'azzardo di Trump",
        "album": "America7",
        "artist": "raiplay sound",
        "date": "2026-03-06",
        "track": "16",
        "disc": "2",
    }


def test_ffmpeg_command_includes_series_metadata_tags(tmp_path: Path) -> None:
    prepared = PreparedDownload(
        episode_id="ep-4",
        episode_label="Episode 4",
        work_dir=tmp_path / "work",
        media_path=tmp_path / "Episode 4.mp3",
        final_path=tmp_path / "Episode 4.m4a",
        info_json_path=None,
        thumbnail_path=None,
        duration_seconds=10.0,
    )

    cmd = _build_ffmpeg_command(
        prepared=prepared,
        audio_format="m4a",
        metadata={
            "title": "L'azzardo di Trump",
            "album": "America7",
            "artist": "raiplay sound",
            "date": "2026-03-06",
            "track": "16",
            "disc": "2",
        },
    )

    assert "-metadata" in cmd
    assert "title=L'azzardo di Trump" in cmd
    assert "album=America7" in cmd
    assert "artist=raiplay sound" in cmd
    assert "track=16" in cmd
    assert "disc=2" in cmd
