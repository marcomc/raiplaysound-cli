from __future__ import annotations

from pathlib import Path
from typing import cast

from rich.progress import TaskID

from raiplaysound_cli.downloads import Downloader, DownloadTask


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
    fake_process = FakeProcess(
        [
            "progress:10:100:0:10.0%",
            "progress:40:100:0:40.0%",
            "progress:100:100:0:100.0%",
        ]
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
    )

    state, detail = downloader.download_one(task)

    assert (state, detail) == ("DONE", "done")
    assert progress.removed == [7]
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
    fake_process = FakeProcess(
        [
            "progress:5000000:10000000:0:50.0%",
            "progress:10000000:10000000:0:100.0%",
        ]
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )
    times = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr("raiplaysound_cli.downloads.time.monotonic", lambda: next(times))

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
        overall_task_id=cast(TaskID, 99),
    )

    state, detail = downloader.download_one(task)

    assert (state, detail) == ("DONE", "done")
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
    assert progress.updated[-1] == {"task_id": 99, "speed_text": ""}


def test_downloader_marks_archive_skip(monkeypatch, tmp_path: Path) -> None:
    progress = RecordingProgress()
    task = DownloadTask(
        episode_id="ep-2",
        episode_url="https://example.test/ep-2",
        episode_label="Episode 2",
        task_id=cast(TaskID, 9),
    )
    fake_process = FakeProcess(
        ["[download] Episode has already been recorded in the archive"],
        returncode=1,
    )
    monkeypatch.setattr(
        "raiplaysound_cli.downloads.subprocess.Popen",
        lambda *args, **kwargs: fake_process,
    )

    downloader = Downloader(
        archive_file=tmp_path / ".download-archive.txt",
        output_template=str(tmp_path / "%(title)s.%(ext)s"),
        audio_format="m4a",
        log_file=None,
        rich_progress=progress,  # type: ignore[arg-type]
        debug_pids=False,
    )

    state, detail = downloader.download_one(task)

    assert (state, detail) == ("SKIP", "downloaded")
    assert progress.updated[-1]["description"] == "skip Episode 2"
    assert progress.removed == [9]
