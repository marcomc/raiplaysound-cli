from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from raiplaysound_cli import daily_sync


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


def test_run_download_passes_config_file_to_cli(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class FakeProcess:
        stdout = iter(["downloaded\n"])

        def wait(self) -> int:
            return 0

    def fake_popen(command: list[str], **_kwargs) -> FakeProcess:
        calls.append(command)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    config_file = tmp_path / "custom.conf"
    log_file = tmp_path / "daily.log"

    result = daily_sync._run_download(
        [str(tmp_path / "raiplaysound-cli")],
        config_file,
        log_file,
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


def test_main_defaults_to_current_python_module_runtime(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        f'FAVORITES="musicalbox"\nTARGET_BASE="{target_base}"\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path]] = []

    def fake_run_download(cli_args, selected_config_file: Path, _log_file: Path) -> int:
        calls.append((list(cli_args), selected_config_file))
        return 0

    monkeypatch.setattr(daily_sync, "_run_download", fake_run_download)
    monkeypatch.setattr(daily_sync, "send_email_summary", lambda **_kwargs: 0)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 0
    assert calls == [([sys.executable, "-m", "raiplaysound_cli"], config_file)]


def test_main_runs_download_when_one_favorite_is_malformed(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "custom.conf"
    target_base = tmp_path / "RaiPlaySound"
    config_file.write_text(
        f'FAVORITES="https://example.test/not-a-program,musicalbox"\nTARGET_BASE="{target_base}"\n',
        encoding="utf-8",
    )
    calls: list[tuple[list[str], Path]] = []
    statuses: list[str] = []

    def fake_run_download(cli_args, selected_config_file: Path, _log_file: Path) -> int:
        calls.append((list(cli_args), selected_config_file))
        return 2

    def fake_send_email_summary(**kwargs) -> int:
        statuses.append(kwargs["status_text"])
        return 0

    monkeypatch.setattr(daily_sync, "_run_download", fake_run_download)
    monkeypatch.setattr(daily_sync, "send_email_summary", fake_send_email_summary)

    result = daily_sync.main(["--config", str(config_file), "--dry-run-email"])

    assert result == 2
    assert calls == [([sys.executable, "-m", "raiplaysound_cli"], config_file)]
    assert statuses == ["failed"]


def test_build_email_body_reports_no_new_downloads() -> None:
    body = daily_sync.build_email_body(status_text="ok", rows=[])

    assert "New episodes downloaded: 0" in body
    assert "No new episodes were downloaded." in body
