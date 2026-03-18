from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from raiplaysound_cli import cli
from raiplaysound_cli.config import Settings
from raiplaysound_cli.models import Program


def test_main_version_prints_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "raiplaysound_cli", "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": "src"},
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    assert "raiplaysound-cli 2.0.0" in result.stdout


def test_main_list_programs_uses_config_filter_and_json(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings.from_config({"STATION_FILTER": "radio2"})
    settings.catalog_cache_file = tmp_path / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(cli, "cache_file_is_fresh", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        cli,
        "collect_program_catalog",
        lambda: [
            Program(
                slug="show-a",
                title="Show A",
                station_name="Radio 2",
                station_short="radio2",
                years="2024",
            ),
            Program(
                slug="show-b",
                title="Show B",
                station_name="Radio 3",
                station_short="radio3",
                years="2025",
            ),
        ],
    )

    result = cli.main(["--programs", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"station_filter": "radio2"' in captured.out
    assert '"slug": "show-a"' in captured.out
    assert '"slug": "show-b"' not in captured.out


def test_list_episodes_does_not_create_download_directory(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "load_show_context",
        lambda *_args, **_kwargs: (
            "america7",
            "https://www.raiplaysound.it/programmi/america7",
            [],
            type("Summary", (), {"has_seasons": False})(),
            settings.target_base / "america7" / ".metadata-cache.tsv",
        ),
    )
    monkeypatch.setattr(cli, "filter_episodes_for_list_or_download", lambda *_args, **_kwargs: [])

    result = cli.main(["--episodes", "america7", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert not (settings.target_base / "america7").exists()
