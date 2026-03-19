from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from raiplaysound_cli import cli
from raiplaysound_cli.config import Settings
from raiplaysound_cli.models import GroupSource, Program


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


def test_main_without_args_prints_extensive_help(capsys) -> None:
    result = cli.main([])
    captured = capsys.readouterr()

    assert result == 0
    assert "usage: raiplaysound-cli [--version] <command>" in captured.out
    assert "Commands:" in captured.out
    assert "list      Inspect stations, programs, seasons, or episodes" in captured.out
    assert "download  Download one program into the local music library" in captured.out
    assert "usage: raiplaysound-cli list" in captured.out
    assert "usage: raiplaysound-cli download" in captured.out
    assert "TARGET_OR_INPUT" in captured.out
    assert "Optional positional target" in captured.out
    assert "--stations" in captured.out
    assert "--episode-ids" in captured.out
    assert "\x1b[" not in captured.out


def test_main_help_prints_extensive_help(capsys) -> None:
    result = cli.main(["--help"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Commands:" in captured.out
    assert "usage: raiplaysound-cli list" in captured.out
    assert "usage: raiplaysound-cli download" in captured.out


def test_main_list_requires_exactly_one_target(capsys) -> None:
    result = cli.main(["list"])
    captured = capsys.readouterr()

    assert result == 1
    assert (
        "list mode requires exactly one target" in captured.err
        or "list mode requires exactly one target" in captured.out
    )


def test_main_list_seasons_positional_target_dispatches(monkeypatch, capsys) -> None:
    settings = Settings.from_config({"COMMAND": "list"})

    def fake_list_seasons(_settings: Settings, args: object) -> int:
        cli.console.print(f"season-input={args.input}")  # type: ignore[attr-defined]
        return 0

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(cli, "list_seasons", fake_list_seasons)

    result = cli.main(["seasons", "america7"])
    captured = capsys.readouterr()

    assert result == 0
    assert "season-input=america7" in captured.out


def test_main_list_episodes_positional_target_dispatches(monkeypatch, capsys) -> None:
    settings = Settings.from_config({"COMMAND": "list"})

    def fake_list_episodes(_settings: Settings, args: object) -> int:
        cli.console.print(f"episode-input={args.input}")  # type: ignore[attr-defined]
        return 0

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(cli, "list_episodes", fake_list_episodes)

    result = cli.main(["episodes", "america7"])
    captured = capsys.readouterr()

    assert result == 0
    assert "episode-input=america7" in captured.out


def test_main_list_seasons_requires_input(capsys) -> None:
    result = cli.main(["list", "--seasons"])
    captured = capsys.readouterr()

    assert result == 1
    assert "list seasons requires <program_slug|program_url>." in captured.err


def test_main_list_episodes_requires_input(capsys) -> None:
    result = cli.main(["list", "--episodes"])
    captured = capsys.readouterr()

    assert result == 1
    assert "list episodes requires <program_slug|program_url>." in captured.err


def test_main_download_requires_input(capsys) -> None:
    result = cli.main(["download"])
    captured = capsys.readouterr()

    assert result == 1
    assert "download requires <program_slug|program_url>." in captured.err


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


def test_list_programs_text_prints_download_suggestion(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
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
            )
        ],
    )

    result = cli.main(["--programs"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Download:" in captured.out
    assert "raiplaysound-cli download <program_slug>" in captured.out


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


def test_list_episodes_aggregates_discovered_groupings(monkeypatch, capsys) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (
            f"https://www.raiplaysound.it/programmi/{slug}",
            [
                GroupSource(
                    key="speciale-pino-daniele",
                    label="Speciale Pino Daniele",
                    url=f"https://www.raiplaysound.it/programmi/{slug}",
                    kind="special",
                ),
                GroupSource(
                    key="speciale-lucio-dalla",
                    label="Speciale Lucio Dalla",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
                    kind="special",
                ),
            ],
        ),
    )

    def fake_load_show_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        for_list_seasons: bool = False,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object, Path]:
        assert input_value == "profili"
        assert for_list_seasons is False
        assert sources_override == [
            "https://www.raiplaysound.it/programmi/profili",
            "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
        ]
        assert source_groups_override is not None
        episodes = [
            type(
                "Episode",
                (),
                {
                    "season": "1",
                    "group_label": "Speciale Pino Daniele",
                    "group_kind": "special",
                    "pretty_date": "2018-06-07",
                    "title": "Speciale Pino Daniele - L'intervista completa",
                    "episode_id": "cd1d7c7a-9306-4768-b258-dce6de1b7383",
                    "url": "https://www.raiplaysound.it/audio/pino.html",
                },
            )(),
            type(
                "Episode",
                (),
                {
                    "season": "1",
                    "group_label": "Speciale Lucio Dalla",
                    "group_kind": "special",
                    "pretty_date": "2018-03-04",
                    "title": "Intervista di Maurizio Federaro a Lucio Dalla",
                    "episode_id": "lucio-1",
                    "url": "https://www.raiplaysound.it/audio/lucio-1.html",
                },
            )(),
        ]
        summary = type("Summary", (), {"has_seasons": False})()
        return (
            "profili",
            "https://www.raiplaysound.it/programmi/profili",
            episodes,
            summary,
            Path("/tmp/.metadata-cache.tsv"),
        )

    monkeypatch.setattr(cli, "load_show_context", fake_load_show_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["--episodes", "profili", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert '"group": "Speciale Pino Daniele"' in captured.out
    assert '"group": "Speciale Lucio Dalla"' in captured.out
    assert '"title": "Speciale Pino Daniele - L\'intervista completa"' in captured.out
    assert '"title": "Intervista di Maurizio Federaro a Lucio Dalla"' in captured.out


def test_main_without_args_ignores_configured_list_seasons(monkeypatch, capsys) -> None:
    settings = Settings.from_config(
        {"COMMAND": "list", "LIST_TARGET": "seasons", "INPUT": "america7"}
    )

    def fail(*_args, **_kwargs) -> None:
        raise AssertionError("empty invocation should print help instead of dispatching")

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(cli, "list_seasons", fail)

    result = cli.main([])
    captured = capsys.readouterr()

    assert result == 0
    assert "Commands:" in captured.out
    assert "usage: raiplaysound-cli list" in captured.out


def test_list_seasons_skips_metadata_refresh_and_cache_writes(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"

    def fail(*_args, **_kwargs) -> None:
        raise AssertionError("metadata path should not be used for list seasons")

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (f"https://www.raiplaysound.it/programmi/{slug}", []),
    )
    monkeypatch.setattr(
        cli,
        "discover_season_listing_sources",
        lambda slug: (
            f"https://www.raiplaysound.it/programmi/{slug}",
            [f"https://www.raiplaysound.it/programmi/{slug}/episodi/stagione-1"],
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_season_summary_from_sources",
        lambda _sources: (
            [],
            type(
                "Summary",
                (),
                {
                    "counts": {"1": 3},
                    "year_min": {"1": "2024"},
                    "year_max": {"1": "2024"},
                    "show_year_min": "2024",
                    "show_year_max": "2024",
                    "has_seasons": True,
                    "latest_season": "1",
                },
            )(),
        ),
    )
    monkeypatch.setattr(cli, "load_show_context", fail)
    monkeypatch.setattr(cli, "collect_metadata", fail)
    monkeypatch.setattr(cli, "write_metadata_cache", fail)

    result = cli.main(["--seasons", "america7", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "seasons"' in captured.out
    assert '"label": "Season 1"' in captured.out
    assert not (settings.target_base / "america7").exists()


def test_list_seasons_prints_groupings_for_special_collections(monkeypatch, capsys) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (
            f"https://www.raiplaysound.it/programmi/{slug}",
            [
                GroupSource(
                    key="speciale-pino-daniele",
                    label="Speciale Pino Daniele",
                    url=f"https://www.raiplaysound.it/programmi/{slug}",
                    kind="special",
                ),
                GroupSource(
                    key="speciale-lucio-dalla",
                    label="Speciale Lucio Dalla",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
                    kind="special",
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_group_summaries",
        lambda _groups: [
            type(
                "GroupSummary",
                (),
                {
                    "key": "speciale-pino-daniele",
                    "label": "Speciale Pino Daniele",
                    "url": "https://www.raiplaysound.it/programmi/profili",
                    "kind": "special",
                    "episodes": 1,
                    "year_min": "2018",
                    "year_max": "2018",
                },
            )(),
            type(
                "GroupSummary",
                (),
                {
                    "key": "speciale-lucio-dalla",
                    "label": "Speciale Lucio Dalla",
                    "url": "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
                    "kind": "special",
                    "episodes": 2,
                    "year_min": "2018",
                    "year_max": "2018",
                },
            )(),
        ],
    )

    result = cli.main(["--seasons", "profili"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Available groupings for profili" in captured.out
    assert "Speciale Pino Daniele: 1 episodes (special; published: 2018)" in captured.out
    assert "Speciale Lucio Dalla: 2 episodes (special; published: 2018)" in captured.out
    assert "all program episodes: raiplaysound-cli download profili" in captured.out


def test_list_seasons_prints_download_suggestions_for_real_seasons(monkeypatch, capsys) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (
            f"https://www.raiplaysound.it/programmi/{slug}",
            [
                GroupSource(
                    key="1",
                    label="Stagione 1",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/episodi/stagione-1",
                    kind="season",
                ),
                GroupSource(
                    key="2",
                    label="Stagione 2",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/episodi/stagione-2",
                    kind="season",
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_group_summaries",
        lambda _groups: [
            type(
                "GroupSummary",
                (),
                {
                    "key": "1",
                    "label": "Stagione 1",
                    "url": "https://www.raiplaysound.it/programmi/america7/episodi/stagione-1",
                    "kind": "season",
                    "episodes": 3,
                    "year_min": "2024",
                    "year_max": "2024",
                },
            )(),
            type(
                "GroupSummary",
                (),
                {
                    "key": "2",
                    "label": "Stagione 2",
                    "url": "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
                    "kind": "season",
                    "episodes": 4,
                    "year_min": "2025",
                    "year_max": "2025",
                },
            )(),
        ],
    )

    result = cli.main(["--seasons", "america7"])
    captured = capsys.readouterr()

    assert result == 0
    assert "all episodes:  raiplaysound-cli download america7" in captured.out
    assert "all seasons:   raiplaysound-cli download america7 --season all" in captured.out
    assert "one season:    raiplaysound-cli download america7 --season 1" in captured.out
    assert "some seasons:  raiplaysound-cli download america7 --season 1,2" in captured.out


def test_main_without_args_ignores_configured_list_episodes(monkeypatch, capsys) -> None:
    settings = Settings.from_config(
        {"COMMAND": "list", "LIST_TARGET": "episodes", "INPUT": "america7"}
    )

    def fail(*_args, **_kwargs) -> None:
        raise AssertionError("empty invocation should print help instead of dispatching")

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(cli, "list_episodes", fail)

    result = cli.main([])
    captured = capsys.readouterr()

    assert result == 0
    assert "Commands:" in captured.out
    assert "usage: raiplaysound-cli download" in captured.out


def test_list_episodes_text_prints_download_suggestions(monkeypatch, capsys) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (f"https://www.raiplaysound.it/programmi/{slug}", []),
    )

    def fake_load_show_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        for_list_seasons: bool = False,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object, Path]:
        assert input_value == "america7"
        assert for_list_seasons is False
        assert sources_override is None
        assert source_groups_override is None
        episodes = [
            type(
                "Episode",
                (),
                {
                    "season": "2",
                    "group_label": "",
                    "group_kind": "",
                    "pretty_date": "2026-03-13",
                    "title": "America7 S2E17",
                    "episode_id": "ep-17",
                    "url": "https://www.raiplaysound.it/audio/ep-17.html",
                },
            )(),
            type(
                "Episode",
                (),
                {
                    "season": "2",
                    "group_label": "",
                    "group_kind": "",
                    "pretty_date": "2026-03-06",
                    "title": "America7 S2E16",
                    "episode_id": "ep-16",
                    "url": "https://www.raiplaysound.it/audio/ep-16.html",
                },
            )(),
        ]
        summary = type("Summary", (), {"has_seasons": True})()
        return (
            "america7",
            "https://www.raiplaysound.it/programmi/america7",
            episodes,
            summary,
            Path("/tmp/.metadata-cache.tsv"),
        )

    monkeypatch.setattr(cli, "load_show_context", fake_load_show_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["--episodes", "america7", "--season", "2"])
    captured = capsys.readouterr()

    assert result == 0
    assert "listed season(s): raiplaysound-cli download america7 --season 2" in captured.out
    assert "all program episodes:   raiplaysound-cli download america7 --season all" in captured.out
    assert "one episode:    raiplaysound-cli download america7 --episode-ids ep-17" in captured.out
    assert (
        "some episodes:  raiplaysound-cli download america7 --episode-ids ep-17,ep-16"
        in captured.out
    )
