from __future__ import annotations

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
        email_from="massaric+raiplaysound-cli@gmail.com",
        email_from_name="RaiPlaySound CLI",
        subject="[raiplaysound-cli] daily favourites sync ok on host",
        body="summary",
        message_date="Sun, 17 May 2026 08:00:00 +0200",
    )

    assert "From: RaiPlaySound CLI <massaric+raiplaysound-cli@gmail.com>" in payload
    assert "To: listener@example.test" in payload
    assert "Subject: [raiplaysound-cli] daily favourites sync ok on host" in payload


def test_build_email_body_reports_no_new_downloads() -> None:
    body = daily_sync.build_email_body(status_text="ok", rows=[])

    assert "New episodes downloaded: 0" in body
    assert "No new episodes were downloaded." in body
