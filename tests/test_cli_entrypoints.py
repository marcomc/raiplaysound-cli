from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from raiplaysound_cli import cli
from raiplaysound_cli import episodes as episode_module
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
    assert "raiplaysound-cli list seasons <program_slug|program_url>" in captured.out
    assert "raiplaysound-cli list episodes <program_slug|program_url>" in captured.out
    assert "usage: raiplaysound-cli list" in captured.out
    assert "usage: raiplaysound-cli download" in captured.out
    assert "TARGET_OR_INPUT" in captured.out
    assert "Preferred positional target" in captured.out
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
        "list mode requires exactly one positional target" in captured.err
        or "list mode requires exactly one positional target" in captured.out
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
    result = cli.main(["list", "seasons"])
    captured = capsys.readouterr()

    assert result == 1
    assert "list seasons requires <program_slug|program_url>." in captured.err


def test_main_list_episodes_requires_input(capsys) -> None:
    result = cli.main(["list", "episodes"])
    captured = capsys.readouterr()

    assert result == 1
    assert "list episodes requires <program_slug|program_url>." in captured.err


def test_main_rejects_legacy_list_target_flags(capsys) -> None:
    result = cli.main(["list", "--episodes", "america7"])
    captured = capsys.readouterr()

    assert result == 2
    assert "unrecognized arguments: --episodes" in captured.err


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

    result = cli.main(["list", "programs", "--json"])
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

    result = cli.main(["list", "programs"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Download:" in captured.out
    assert "raiplaysound-cli download <program_slug>" in captured.out


def test_list_episodes_does_not_create_download_directory(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )
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

    result = cli.main(["list", "episodes", "america7", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert not (settings.target_base / "america7").exists()


def test_list_episodes_skips_metadata_refresh_and_cache_writes(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"

    def fail(*_args, **_kwargs) -> None:
        raise AssertionError("list episodes should not refresh or write metadata cache")

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )
    monkeypatch.setattr(cli, "load_show_context", fail)
    monkeypatch.setattr(cli, "collect_metadata", fail)
    monkeypatch.setattr(cli, "write_metadata_cache", fail)
    monkeypatch.setattr(
        cli,
        "load_list_episode_context",
        lambda *_args, **_kwargs: (
            "musicalbox",
            "https://www.raiplaysound.it/programmi/musicalbox",
            [
                type(
                    "Episode",
                    (),
                    {
                        "season": "",
                        "group_label": "",
                        "group_kind": "",
                        "pretty_date": "2026-03-16",
                        "title": "Musical Box del 15/03/2026",
                        "episode_id": "ep-1",
                        "url": "https://www.raiplaysound.it/audio/ep-1.html",
                    },
                )(),
            ],
            type("Summary", (), {"has_seasons": False, "latest_season": "1"})(),
        ),
    )
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "musicalbox", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert '"title": "Musical Box del 15/03/2026"' in captured.out
    assert not (settings.target_base / "musicalbox").exists()


def test_list_episodes_uses_cached_payload(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"
    cache_file = settings.catalog_cache_file.parent / "list-episodes" / "profili-cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        """
{
  "version": 3,
  "slug": "profili",
  "program_url": "https://www.raiplaysound.it/programmi/profili",
  "summary": {
    "has_seasons": false,
    "latest_season": "1",
    "show_year_min": "2018",
    "show_year_max": "2018",
    "counts": {"1": 2},
    "year_min": {"1": "2018"},
    "year_max": {"1": "2018"}
  },
  "episodes": [
    {
      "episode_id": "ep-1",
      "url": "https://www.raiplaysound.it/audio/ep-1.html",
      "label": "ep-1",
      "title": "Intervista a Lucio Dalla",
      "upload_date": "20180302",
      "season": "1",
      "year": "2018",
      "group_label": "Speciale Lucio Dalla",
      "group_kind": "special"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (
            ["https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla"],
            [
                GroupSource(
                    key="speciale-lucio-dalla",
                    label="Speciale Lucio Dalla",
                    url="https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
                    kind="special",
                )
            ],
            True,
        ),
    )
    monkeypatch.setattr(cli, "_episode_list_cache_file", lambda *_args, **_kwargs: cache_file)
    monkeypatch.setattr(
        cli,
        "load_list_episode_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fresh episode cache should avoid live recomputation")
        ),
    )
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "profili"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Speciale Lucio Dalla" in captured.out
    assert "Intervista a Lucio Dalla" in captured.out


def test_list_episodes_cache_key_uses_resolved_season_sources(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )

    captured_sources: list[list[str]] = []

    def fake_episode_list_cache_file(_settings: Settings, _slug: str, sources: list[str]) -> Path:
        captured_sources.append(sources)
        return tmp_path / "state" / "list-episodes" / "america7.json"

    monkeypatch.setattr(cli, "_episode_list_cache_file", fake_episode_list_cache_file)
    monkeypatch.setattr(
        cli,
        "discover_feed_sources",
        lambda slug, selected_seasons, _request_all, _for_list: (
            [f"https://www.raiplaysound.it/programmi/{slug}/episodi/stagione-2"]
            if selected_seasons == {"2"}
            else [f"https://www.raiplaysound.it/programmi/{slug}"]
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_list_episode_context",
        lambda *_args, **_kwargs: (
            "america7",
            "https://www.raiplaysound.it/programmi/america7",
            [],
            type(
                "Summary",
                (),
                {
                    "has_seasons": True,
                    "latest_season": "2",
                    "show_year_min": "2025",
                    "show_year_max": "2026",
                    "counts": {"2": 0},
                    "year_min": {"2": "2025"},
                    "year_max": {"2": "2026"},
                },
            )(),
        ),
    )
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "america7", "--season", "2", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert captured_sources == [
        ["https://www.raiplaysound.it/programmi/america7/episodi/stagione-2"]
    ]


def test_list_episodes_aggregates_discovered_groupings(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda slug, _selected_seasons, _request_all, _selected_groups: (
            [
                f"https://www.raiplaysound.it/programmi/{slug}",
                f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
            ],
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
            True,
        ),
    )

    def fake_load_list_episode_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object]:
        assert input_value == "profili"
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
        )

    monkeypatch.setattr(cli, "load_list_episode_context", fake_load_list_episode_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "profili", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "episodes"' in captured.out
    assert '"group": "Speciale Pino Daniele"' in captured.out
    assert '"group": "Speciale Lucio Dalla"' in captured.out
    assert '"title": "Speciale Pino Daniele - L\'intervista completa"' in captured.out
    assert '"title": "Intervista di Maurizio Federaro a Lucio Dalla"' in captured.out


def test_list_episodes_filters_by_group(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda slug, _selected_seasons, _request_all, selected_groups: (
            [f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla"],
            [
                GroupSource(
                    key="speciale-lucio-dalla",
                    label="Speciale Lucio Dalla",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
                    kind="special",
                ),
            ],
            bool(selected_groups),
        ),
    )

    def fake_load_list_episode_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object]:
        assert input_value == "profili"
        assert sources_override == [
            "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla"
        ]
        assert [group.label for group in source_groups_override or []] == ["Speciale Lucio Dalla"]
        episodes = [
            type(
                "Episode",
                (),
                {
                    "season": "",
                    "group_label": "Speciale Lucio Dalla",
                    "group_kind": "special",
                    "pretty_date": "2018-03-02",
                    "title": "Intervista a Lucio Dalla",
                    "episode_id": "ep-2",
                    "url": "https://www.raiplaysound.it/audio/ep-2.html",
                },
            )(),
        ]
        summary = type("Summary", (), {"has_seasons": False})()
        return (
            "profili",
            "https://www.raiplaysound.it/programmi/profili",
            episodes,
            summary,
        )

    monkeypatch.setattr(cli, "load_list_episode_context", fake_load_list_episode_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "profili", "--group", "speciale-lucio-dalla"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Speciale Lucio Dalla" in captured.out
    assert "Intervista a Lucio Dalla" in captured.out


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
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"
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

    result = cli.main(["list", "seasons", "america7", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "seasons"' in captured.out
    assert '"label": "Season 1"' in captured.out
    assert not (settings.target_base / "america7").exists()


def test_list_seasons_uses_cached_summary_payload(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"
    cache_file = settings.catalog_cache_file.parent / "list-seasons" / "america7.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        """
{
  "version": 3,
  "slug": "america7",
  "program_url": "https://www.raiplaysound.it/programmi/america7",
  "has_seasons": true,
  "has_groups": false,
  "items": [
    {
      "key": "2",
      "label": "Season 2",
      "kind": "season",
      "episodes": 17,
      "published": "2025-2026",
      "url": "https://www.raiplaysound.it/programmi/america7/stagione-2"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "_build_season_listing_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fresh season cache should avoid live recomputation")
        ),
    )

    result = cli.main(["list", "seasons", "america7"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Season 2: 17 episodes" in captured.out


def test_list_seasons_json_uses_real_discovered_season_urls(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

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
            [f"https://www.raiplaysound.it/programmi/{slug}/puntate/stagione-1"],
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

    result = cli.main(["list", "seasons", "america7", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert (
        '"url": "https://www.raiplaysound.it/programmi/america7/puntate/stagione-1"' in captured.out
    )


def test_list_seasons_prints_groupings_for_special_collections(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

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

    result = cli.main(["list", "seasons", "profili"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Available groupings for profili" in captured.out
    assert "Speciale Pino Daniele: 1 episodes" in captured.out
    assert "select with --group" in captured.out
    assert "speciale-pino-daniele" in captured.out
    assert "Speciale Lucio Dalla: 2 episodes" in captured.out
    assert "speciale-lucio-dalla" in captured.out
    assert "all program episodes: raiplaysound-cli download profili" in captured.out
    assert (
        "speciale-pino-daniele: raiplaysound-cli download profili --group "
        "speciale-pino-daniele" in captured.out
    )
    assert (
        "speciale-lucio-dalla: raiplaysound-cli download profili --group "
        "speciale-lucio-dalla" in captured.out
    )


def test_list_seasons_prints_download_suggestions_for_real_seasons(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

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

    result = cli.main(["list", "seasons", "america7"])
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


def test_list_episodes_text_prints_download_suggestions(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )

    def fake_load_list_episode_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object]:
        assert input_value == "america7"
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
        )

    monkeypatch.setattr(cli, "load_list_episode_context", fake_load_list_episode_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "america7", "--season", "2"])
    captured = capsys.readouterr()

    assert result == 0
    assert "listed season(s): raiplaysound-cli download america7 --season 2" in captured.out
    assert "all program episodes:   raiplaysound-cli download america7 --season all" in captured.out
    assert "one episode:    raiplaysound-cli download america7 --episode-ids ep-17" in captured.out
    assert (
        "some episodes:  raiplaysound-cli download america7 --episode-ids ep-17,ep-16"
        in captured.out
    )


def test_flat_program_outputs_do_not_invent_season_one(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

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
        lambda slug: (f"https://www.raiplaysound.it/programmi/{slug}", []),
    )
    monkeypatch.setattr(
        cli,
        "collect_season_summary_from_sources",
        lambda _sources: (
            [
                type(
                    "Episode",
                    (),
                    {
                        "season": "1",
                        "group_label": "",
                        "group_kind": "",
                        "pretty_date": "2026-02-21",
                        "title": "Standalone episode",
                        "episode_id": "ep-1",
                        "url": "https://www.raiplaysound.it/audio/ep-1.html",
                    },
                )()
            ],
            type(
                "Summary",
                (),
                {
                    "counts": {"1": 1},
                    "year_min": {"1": "2026"},
                    "year_max": {"1": "2026"},
                    "show_year_min": "2026",
                    "show_year_max": "2026",
                    "has_seasons": False,
                    "latest_season": "1",
                },
            )(),
        ),
    )

    result = cli.main(["list", "seasons", "flat-show", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"label": "All episodes"' in captured.out
    assert '"kind": "flat"' in captured.out
    assert '"label": "Season 1"' not in captured.out


def test_flat_program_episode_listing_omits_season_column(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )
    monkeypatch.setattr(
        cli,
        "discover_feed_sources",
        lambda slug, _selected_seasons, _request_all, _for_list: [
            f"https://www.raiplaysound.it/programmi/{slug}"
        ],
    )

    def fake_load_list_episode_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object]:
        assert input_value == "flat-show"
        assert sources_override is None
        assert source_groups_override is None
        episodes = [
            type(
                "Episode",
                (),
                {
                    "season": "1",
                    "group_label": "",
                    "group_kind": "",
                    "pretty_date": "2026-02-21",
                    "title": "Standalone episode",
                    "episode_id": "ep-1",
                    "url": "https://www.raiplaysound.it/audio/ep-1.html",
                },
            )()
        ]
        summary = type("Summary", (), {"has_seasons": False})()
        return (
            "flat-show",
            "https://www.raiplaysound.it/programmi/flat-show",
            episodes,
            summary,
        )

    monkeypatch.setattr(cli, "load_list_episode_context", fake_load_list_episode_context)
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )

    result = cli.main(["list", "episodes", "flat-show"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Season" not in captured.out
    assert "S1" not in captured.out
    assert "Standalone episode" in captured.out


def test_collect_episodes_from_flat_source_does_not_mark_real_season(monkeypatch) -> None:
    monkeypatch.setattr(
        episode_module,
        "run_yt_dlp",
        lambda _args, allow_partial_failure=False: type(
            "Result",
            (),
            {
                "stdout": (
                    "ep-1\thttps://www.raiplaysound.it/audio/2026/03/16/"
                    "musical-box-del-15-03-2026-ep-1.html\n"
                )
            },
        )(),
    )

    episodes = cli.collect_episodes_from_sources(
        ["https://www.raiplaysound.it/programmi/musicalbox"]
    )

    assert len(episodes) == 1
    assert episodes[0].season == ""


def test_list_seasons_honors_season_filter_for_real_seasons(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

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
                    "episodes": 71,
                    "year_min": "2023",
                    "year_max": "2025",
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
                    "episodes": 17,
                    "year_min": "2025",
                    "year_max": "2026",
                },
            )(),
        ],
    )

    result = cli.main(["list", "seasons", "america7", "--season", "2"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Season 2: 17 episodes" in captured.out
    assert "Season 1: 71 episodes" not in captured.out


def test_list_seasons_rejects_season_filter_for_non_season_groupings(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.catalog_cache_file = tmp_path / "state" / "program-catalog.tsv"

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {"COMMAND": "list"})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_group_listing_sources",
        lambda slug: (
            f"https://www.raiplaysound.it/programmi/{slug}",
            [
                GroupSource(
                    key="speciale-lucio-dalla",
                    label="Speciale Lucio Dalla",
                    url=f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
                    kind="special",
                )
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
                    "key": "speciale-lucio-dalla",
                    "label": "Speciale Lucio Dalla",
                    "url": "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
                    "kind": "special",
                    "episodes": 3,
                    "year_min": "2018",
                    "year_max": "2018",
                },
            )()
        ],
    )

    result = cli.main(["list", "seasons", "profili", "--season", "1"])
    captured = capsys.readouterr()

    assert result == 1
    assert "this program does not expose seasons" in captured.err


def test_download_uses_grouped_episode_sources(monkeypatch, tmp_path: Path, capsys) -> None:
    settings = Settings()
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"
    settings.jobs = 1
    settings.check_jobs = 1

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda slug, _selected_seasons, _request_all, selected_groups: (
            [
                f"https://www.raiplaysound.it/programmi/{slug}",
                f"https://www.raiplaysound.it/programmi/{slug}/speciali/speciale-lucio-dalla",
            ],
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
            bool(selected_groups),
        ),
    )

    def fake_load_cached_show_context(
        _settings: Settings,
        input_value: str,
        _selected_seasons: set[str],
        _request_all: bool,
        *,
        sources_override: list[str] | None = None,
        source_groups_override: list[GroupSource] | None = None,
    ) -> tuple[str, str, list[object], object, Path, dict[str, tuple[str, str, str]]]:
        assert input_value == "profili"
        assert sources_override == [
            "https://www.raiplaysound.it/programmi/profili",
            "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
        ]
        assert [group.label for group in source_groups_override or []] == [
            "Speciale Pino Daniele",
            "Speciale Lucio Dalla",
        ]
        episodes = [
            type(
                "Episode",
                (),
                {
                    "season": "",
                    "group_label": "Speciale Pino Daniele",
                    "group_kind": "special",
                    "pretty_date": "2018-06-07",
                    "title": "Speciale Pino Daniele - L'intervista completa",
                    "label": "speciale-pino-daniele",
                    "episode_id": "ep-1",
                    "url": "https://www.raiplaysound.it/audio/ep-1.html",
                },
            )(),
            type(
                "Episode",
                (),
                {
                    "season": "",
                    "group_label": "Speciale Lucio Dalla",
                    "group_kind": "special",
                    "pretty_date": "2018-03-04",
                    "title": "Intervista di Maurizio Federaro a Lucio Dalla",
                    "label": "speciale-lucio-dalla",
                    "episode_id": "ep-2",
                    "url": "https://www.raiplaysound.it/audio/ep-2.html",
                },
            )(),
        ]
        summary = type("Summary", (), {"has_seasons": True, "latest_season": "1"})()
        return (
            "profili",
            "https://www.raiplaysound.it/programmi/profili",
            episodes,
            summary,
            settings.target_base / "profili" / ".metadata-cache.tsv",
            {},
        )

    monkeypatch.setattr(cli, "load_cached_show_context", fake_load_cached_show_context)

    def fake_filter_episodes(
        episodes: list[object],
        summary: object,
        *_args: object,
        **_kwargs: object,
    ) -> list[object]:
        summary.has_seasons = False  # type: ignore[attr-defined]
        return episodes

    monkeypatch.setattr(cli, "filter_episodes_for_list_or_download", fake_filter_episodes)
    monkeypatch.setattr(cli, "predicted_media_exists", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(cli, "acquire_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_log_file", lambda **_kwargs: None)

    class FakeDownloader:
        def __init__(self, **_kwargs) -> None:
            self.tasks: list[object] = []

        def download_one(self, task: object) -> tuple[str, str]:
            self.tasks.append(task)
            return "DONE", "done"

        def terminate_all(self) -> None:
            return None

    monkeypatch.setattr(cli, "Downloader", FakeDownloader)

    result = cli.main(["download", "profili", "--group", "speciale-lucio-dalla"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Completed: done=2, skipped=0, errors=0" in captured.out


def test_download_refreshes_metadata_only_for_filtered_episodes(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"
    settings.jobs = 1
    settings.check_jobs = 1

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )

    episodes = [
        type(
            "Episode",
            (),
            {
                "season": "2",
                "group_label": "",
                "group_kind": "",
                "pretty_date": "NA",
                "title": "Episode One",
                "label": "episode-one",
                "episode_id": "ep-1",
                "url": "https://www.raiplaysound.it/audio/ep-1.html",
            },
        )(),
        type(
            "Episode",
            (),
            {
                "season": "2",
                "group_label": "",
                "group_kind": "",
                "pretty_date": "NA",
                "title": "Episode Two",
                "label": "episode-two",
                "episode_id": "ep-2",
                "url": "https://www.raiplaysound.it/audio/ep-2.html",
            },
        )(),
    ]
    summary = type("Summary", (), {"has_seasons": True, "latest_season": "2"})()

    monkeypatch.setattr(
        cli,
        "load_cached_show_context",
        lambda *_args, **_kwargs: (
            "america7",
            "https://www.raiplaysound.it/programmi/america7",
            episodes,
            summary,
            settings.target_base / "america7" / ".metadata-cache.tsv",
            {},
        ),
    )
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda _episodes, *_args, **_kwargs: [episodes[1]],
    )

    captured_targets: list[list[str]] = []

    def fake_collect_metadata(
        targets: list[str], *, single_entries: bool = False
    ) -> dict[str, tuple[str, str, str]]:
        captured_targets.append(targets)
        assert single_entries is True
        return {"ep-2": ("20260306", "2", "Episode Two")}

    written_cache: dict[str, tuple[str, str, str]] = {}

    monkeypatch.setattr(cli, "collect_metadata", fake_collect_metadata)
    monkeypatch.setattr(
        cli,
        "write_metadata_cache",
        lambda _path, cache: written_cache.update(cache),
    )
    monkeypatch.setattr(cli, "predicted_media_exists", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(cli, "acquire_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_log_file", lambda **_kwargs: None)

    class FakeDownloader:
        def __init__(self, **_kwargs) -> None:
            return None

        def download_one(self, task: object) -> tuple[str, str]:
            return "DONE", "done"

        def terminate_all(self) -> None:
            return None

    monkeypatch.setattr(cli, "Downloader", FakeDownloader)

    result = cli.main(["download", "america7", "--episode-ids", "ep-2"])
    captured = capsys.readouterr()

    assert result == 0
    assert captured_targets == [["https://www.raiplaysound.it/audio/ep-2.html"]]
    assert written_cache == {"ep-2": ("20260306", "2", "Episode Two")}
    assert "Completed: done=1, skipped=0, errors=0" in captured.out


def test_download_skips_missing_scan_when_missing_not_enabled(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    settings = Settings()
    settings.target_base = tmp_path / "Music" / "RaiPlaySound"
    settings.jobs = 1
    settings.check_jobs = 1
    target_dir = settings.target_base / "america7"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / ".download-archive.txt").write_text("raiplaysound ep-1\n", encoding="utf-8")

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "discover_grouped_episode_sources",
        lambda _slug, _selected_seasons, _request_all, _selected_groups: (None, None, False),
    )
    monkeypatch.setattr(
        cli,
        "load_cached_show_context",
        lambda *_args, **_kwargs: (
            "america7",
            "https://www.raiplaysound.it/programmi/america7",
            [
                type(
                    "Episode",
                    (),
                    {
                        "season": "2",
                        "group_label": "",
                        "group_kind": "",
                        "pretty_date": "2026-03-06",
                        "title": "Episode Two",
                        "label": "episode-two",
                        "episode_id": "ep-1",
                        "url": "https://www.raiplaysound.it/audio/ep-1.html",
                        "upload_date": "20260306",
                        "year": "2026",
                    },
                )()
            ],
            type(
                "Summary",
                (),
                {
                    "has_seasons": True,
                    "latest_season": "2",
                    "counts": {"2": 1},
                    "year_min": {"2": "2026"},
                    "year_max": {"2": "2026"},
                    "show_year_min": "2026",
                    "show_year_max": "2026",
                },
            )(),
            target_dir / ".metadata-cache.tsv",
            {"ep-1": ("20260306", "2", "Episode Two")},
        ),
    )
    monkeypatch.setattr(
        cli,
        "filter_episodes_for_list_or_download",
        lambda episodes, *_args, **_kwargs: episodes,
    )
    monkeypatch.setattr(
        cli,
        "predicted_media_exists",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing scan should be skipped unless --missing is enabled")
        ),
    )
    monkeypatch.setattr(cli, "acquire_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "resolve_log_file", lambda **_kwargs: None)

    class FakeDownloader:
        def __init__(self, **_kwargs) -> None:
            return None

        def download_one(self, task: object) -> tuple[str, str]:
            return "DONE", "done"

        def terminate_all(self) -> None:
            return None

    monkeypatch.setattr(cli, "Downloader", FakeDownloader)

    result = cli.main(["download", "america7"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Completed: done=1, skipped=0, errors=0" in captured.out
