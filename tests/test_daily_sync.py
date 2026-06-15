from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from raiplaysound_cli import daily_sync
from raiplaysound_cli.runtime import ProcessRunResult


def test_build_report_groups_new_downloads_with_metadata(tmp_path: Path) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    old_file = show_dir / "Musical Box - 2026-05-10 - Old episode.m4a"
    old_file.write_bytes(b"old")
    new_file = show_dir / "Musical Box - 2026-05-17 - New episode.m4a"
    new_file.write_bytes(b"new")

    rows = daily_sync.build_download_rows(
        target_base=tmp_path,
        favorites=["musicalbox"],
        before={old_file},
        after={old_file, new_file},
    )

    assert rows == [
        daily_sync.DownloadRow(
            program="musicalbox",
            episode_date="2026-05-17",
            title="New episode",
            file_name="Musical Box - 2026-05-17 - New episode.m4a",
        )
    ]


def test_build_email_body_includes_borderless_table_for_downloads() -> None:
    body = daily_sync.build_email_body(
        status_text="ok",
        rows=[
            daily_sync.DownloadRow(
                program="musicalbox",
                episode_date="2026-05-17",
                title="Musical Box del 17/05/2026",
                file_name="Musical Box - 2026-05-17 - Musical Box del 17⧸05⧸2026.m4a",
            )
        ],
    )

    assert "New episodes downloaded: 1" in body
    assert "Program     Date        Title" in body
    assert "musicalbox  2026-05-17  Musical Box del 17/05/2026" in body
    assert "|" not in body


def test_build_email_payload_uses_configured_from_address() -> None:
    payload = daily_sync.build_email_payload(
        email_to="listener@example.test",
        email_from="listener+raiplaysound-cli@example.test",
        email_from_name="RaiPlaySound CLI",
        subject="[raiplaysound-cli] daily favourites sync ok on host",
        body="summary",
        message_date="Sun, 17 May 2026 08:00:00 +0200",
    )

    assert "From: RaiPlaySound CLI <listener+raiplaysound-cli@example.test>" in payload
    assert "To: listener@example.test" in payload
    assert "Subject: [raiplaysound-cli] daily favourites sync ok on host" in payload


def test_send_email_summary_dry_run_does_not_require_msmtp(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(daily_sync.shutil, "which", lambda _name: None)
    log_file = tmp_path / "daily.log"

    result = daily_sync.send_email_summary(
        config={
            "EMAIL_TO": "listener@example.test",
            "EMAIL_FROM": "listener+raiplaysound-cli@example.test",
        },
        status_text="ok",
        rows=[],
        dry_run=True,
        log_file=log_file,
    )

    assert result == 0
    assert "To: listener@example.test" in capsys.readouterr().out
    assert "Email dry run enabled" in log_file.read_text(encoding="utf-8")


def test_send_email_summary_times_out_msmtp(monkeypatch, tmp_path: Path) -> None:
    email_config = tmp_path / "msmtp.conf"
    email_config.write_text("from listener+raiplaysound-cli@example.test\n", encoding="utf-8")
    log_file = tmp_path / "daily.log"

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="msmtp", timeout=3)

    monkeypatch.setattr(daily_sync.shutil, "which", lambda _name: "/usr/bin/msmtp")
    monkeypatch.setattr(daily_sync.subprocess, "run", fake_run)

    result = daily_sync.send_email_summary(
        config={
            "EMAIL_TO": "listener@example.test",
            "EMAIL_CONFIG": str(email_config),
            "MSMTP_BIN": "msmtp",
        },
        status_text="failed",
        rows=[],
        dry_run=False,
        log_file=log_file,
        timeout_seconds=3,
    )

    assert result == 124
    assert "Email summary timed out after 3s." in log_file.read_text(encoding="utf-8")


def test_run_download_passes_config_file_to_cli(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    timeouts: list[int] = []

    def fake_run_streamed_process(command: list[str], **kwargs: object) -> ProcessRunResult:
        calls.append(command)
        timeouts.append(cast(int, kwargs["timeout_seconds"]))
        on_line = cast(Callable[[str], None], kwargs["on_line"])
        on_line("downloaded")
        return ProcessRunResult(0)

    monkeypatch.setattr(daily_sync, "run_streamed_process", fake_run_streamed_process)
    config_file = tmp_path / "custom.conf"
    log_file = tmp_path / "daily.log"

    result = daily_sync._run_download(
        [str(tmp_path / "raiplaysound-cli")],
        config_file,
        log_file,
        timeout_seconds=42,
    )

    assert result == 0
    assert calls == [
        [
            str(tmp_path / "raiplaysound-cli"),
            "--config",
            str(config_file),
            "download",
            "--favourites",
        ]
    ]
    assert timeouts == [42]
    assert "downloaded" in log_file.read_text(encoding="utf-8")


def test_main_defaults_to_current_python_module_runtime(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        f'FAVORITES="musicalbox"\nTARGET_BASE="{target_base}"\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path]] = []
    timeouts: list[int] = []
    snapshot_timeouts: list[int] = []

    def fake_run_download(
        cli_args,
        selected_config_file: Path,
        _log_file: Path,
        *,
        timeout_seconds: int,
    ) -> int:
        calls.append((list(cli_args), selected_config_file))
        timeouts.append(timeout_seconds)
        return 0

    def fake_snapshot_audio_files(
        _target_base: Path,
        _slugs: list[str],
        *,
        timeout_seconds: int,
    ) -> tuple[set[Path], str]:
        snapshot_timeouts.append(timeout_seconds)
        return set(), ""

    monkeypatch.setattr(daily_sync, "_run_download", fake_run_download)
    monkeypatch.setattr(daily_sync, "_snapshot_audio_files", fake_snapshot_audio_files)
    monkeypatch.setattr(daily_sync, "send_email_summary", lambda **_kwargs: 0)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 0
    assert calls == [([sys.executable, "-m", "raiplaysound_cli"], config_file)]
    assert timeouts == [9000]
    assert snapshot_timeouts == [120, 120]


def test_main_applies_daily_sync_max_to_entire_wrapper(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        "\n".join(
            [
                'FAVORITES="musicalbox"',
                f'TARGET_BASE="{target_base}"',
                "DAILY_SYNC_MAX_SECONDS=100",
                "DAILY_SYNC_SCAN_TIMEOUT_SECONDS=120",
            ]
        ),
        encoding="utf-8",
    )
    clock = {"now": 0.0}
    snapshot_timeouts: list[int] = []
    download_timeouts: list[int] = []
    email_timeouts: list[int] = []

    def fake_monotonic() -> float:
        return clock["now"]

    def fake_snapshot_audio_files(
        _target_base: Path,
        _slugs: list[str],
        *,
        timeout_seconds: int,
    ) -> tuple[set[Path], str]:
        snapshot_timeouts.append(timeout_seconds)
        clock["now"] = 10.0 if len(snapshot_timeouts) == 1 else 96.0
        return set(), ""

    def fake_run_download(
        _cli_args,
        _selected_config_file: Path,
        _log_file: Path,
        *,
        timeout_seconds: int,
    ) -> int:
        download_timeouts.append(timeout_seconds)
        clock["now"] = 95.0
        return 0

    def fake_send_email_summary(**kwargs) -> int:
        email_timeouts.append(kwargs["timeout_seconds"])
        return 0

    monkeypatch.setattr(daily_sync.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(daily_sync, "_snapshot_audio_files", fake_snapshot_audio_files)
    monkeypatch.setattr(daily_sync, "_run_download", fake_run_download)
    monkeypatch.setattr(daily_sync, "send_email_summary", fake_send_email_summary)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 0
    assert snapshot_timeouts == [100, 5]
    assert download_timeouts == [90]
    assert email_timeouts == [4]


def test_main_runs_download_when_one_favorite_is_malformed(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        f'FAVORITES="https://example.test/not-a-program,musicalbox"\nTARGET_BASE="{target_base}"\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path]] = []
    statuses: list[str] = []

    def fake_run_download(
        cli_args,
        selected_config_file: Path,
        _log_file: Path,
        *,
        timeout_seconds: int,
    ) -> int:
        assert timeout_seconds == 9000
        calls.append((list(cli_args), selected_config_file))
        return 2

    def fake_snapshot_audio_files(
        _target_base: Path,
        _slugs: list[str],
        *,
        timeout_seconds: int,
    ) -> tuple[set[Path], str]:
        assert timeout_seconds == 120
        return set(), ""

    def fake_send_email_summary(**kwargs) -> int:
        statuses.append(kwargs["status_text"])
        return 0

    monkeypatch.setattr(daily_sync, "_run_download", fake_run_download)
    monkeypatch.setattr(daily_sync, "_snapshot_audio_files", fake_snapshot_audio_files)
    monkeypatch.setattr(daily_sync, "send_email_summary", fake_send_email_summary)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 2
    assert calls == [([sys.executable, "-m", "raiplaysound_cli"], config_file)]
    assert statuses == ["failed"]


def test_main_marks_failed_when_audio_snapshot_times_out(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        f'FAVORITES="musicalbox"\nTARGET_BASE="{target_base}"\n',
        encoding="utf-8",
    )
    statuses: list[str] = []
    rows_seen: list[list[daily_sync.DownloadRow]] = []
    existing_file = target_base / "musicalbox" / "existing.mp3"
    snapshot_results: list[tuple[set[Path], str]] = [
        (set(), ""),
        ({existing_file}, "audio file snapshot timed out after 120s"),
    ]

    def fake_snapshot_audio_files(
        _target_base: Path,
        _slugs: list[str],
        *,
        timeout_seconds: int,
    ) -> tuple[set[Path], str]:
        assert timeout_seconds == 120
        return snapshot_results.pop(0)

    def fake_send_email_summary(**kwargs) -> int:
        statuses.append(kwargs["status_text"])
        rows_seen.append(list(kwargs["rows"]))
        return 0

    monkeypatch.setattr(daily_sync, "_snapshot_audio_files", fake_snapshot_audio_files)
    monkeypatch.setattr(daily_sync, "_run_download", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(daily_sync, "send_email_summary", fake_send_email_summary)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 1
    assert statuses == ["failed"]
    assert rows_seen == [[]]


def test_snapshot_audio_files_collects_paths_with_timeout(tmp_path: Path) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    audio_file = show_dir / "episode.mp3"
    audio_file.write_bytes(b"audio")
    ignored_file = show_dir / "cover.jpg"
    ignored_file.write_bytes(b"image")

    files, error = daily_sync._snapshot_audio_files(
        tmp_path,
        ["musicalbox"],
        timeout_seconds=10,
    )

    assert files == {audio_file}
    assert error == ""


def test_snapshot_audio_files_handles_many_paths_without_queue_deadlock(tmp_path: Path) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    expected_files = set()
    for index in range(1200):
        audio_file = show_dir / f"episode-{index:04d}-{'x' * 80}.mp3"
        audio_file.write_bytes(b"audio")
        expected_files.add(audio_file)

    files, error = daily_sync._snapshot_audio_files(
        tmp_path,
        ["musicalbox"],
        timeout_seconds=10,
    )

    assert error == ""
    assert files == expected_files


def test_build_email_body_reports_no_new_downloads() -> None:
    body = daily_sync.build_email_body(status_text="ok", rows=[])

    assert "New episodes downloaded: 0" in body
    assert "No new episodes were downloaded." in body
