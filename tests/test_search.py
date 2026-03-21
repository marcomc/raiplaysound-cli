from __future__ import annotations

import json
from pathlib import Path

from raiplaysound_cli import cli
from raiplaysound_cli.config import Settings
from raiplaysound_cli.search import search_local_episodes, search_local_groupings


def test_search_help_prints_command_specific_help(capsys) -> None:
    result = cli.main(["search", "--help"])
    captured = capsys.readouterr()

    assert result == 0
    assert "usage: raiplaysound-cli search QUERY [QUERY ...] [options]" in captured.out
    assert "Search RaiPlaySound stations and programs" in captured.out
    assert "Output:" in captured.out
    assert "Catalog:" in captured.out
    assert "--show-urls" in captured.out
    assert "--refresh-catalog" in captured.out


def test_search_command_json_uses_grouped_results(monkeypatch, capsys) -> None:
    settings = Settings()

    monkeypatch.setattr(cli, "parse_env_file", lambda _path: {})
    monkeypatch.setattr(cli.Settings, "from_config", classmethod(lambda cls, _config: settings))
    monkeypatch.setattr(
        cli,
        "search_all",
        lambda *_args, **_kwargs: {
            "query": "lucio dalla",
            "stations": [{"name": "Rai Radio 2", "slug": "radio2", "page_url": "", "feed_url": ""}],
            "programs": [],
            "groupings": [
                {
                    "slug": "profili",
                    "label": "Speciale Lucio Dalla",
                    "key": "speciale-lucio-dalla",
                    "kind": "special",
                    "published": "2024",
                    "url": "",
                    "episodes": 1,
                    "all_seasons": False,
                }
            ],
            "episodes": [
                {
                    "slug": "profili",
                    "program_url": "",
                    "title": "Lucio Dalla raccontato",
                    "date": "2024-01-01",
                    "season": "NA",
                    "group": "Speciale Lucio Dalla",
                    "group_kind": "special",
                    "id": "ep-1",
                    "url": "",
                }
            ],
            "local_episode_metadata": True,
            "cache_info": {
                "stations": {"source": "live"},
                "programs": {"source": "cache", "age": "2 days old"},
                "groupings": {"source": "cache", "age": "5 days old"},
                "episodes": {"source": "cache", "age": "7 days old"},
            },
            "refresh_hint": "raiplaysound-cli list programs --refresh-catalog",
        },
    )

    result = cli.main(["search", "lucio", "dalla", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"mode": "search"' in captured.out
    assert '"query": "lucio dalla"' in captured.out
    assert '"stations": 1' in captured.out
    assert '"groupings": 1' in captured.out
    assert '"episodes": 1' in captured.out
    assert '"refresh_hint": "raiplaysound-cli list programs --refresh-catalog"' in captured.out


def test_search_results_print_cache_hints(capsys) -> None:
    cli.print_search_results(
        {
            "query": "radio2",
            "stations": [],
            "programs": [],
            "groupings": [],
            "episodes": [],
            "cache_info": {
                "stations": {"source": "live"},
                "programs": {"source": "cache", "age": "2 days old"},
                "groupings": {"source": "cache", "age": "4 days old"},
                "episodes": {"source": "cache", "age": "6 days old"},
            },
            "refresh_hint": "raiplaysound-cli list programs --refresh-catalog",
        },
        show_urls=False,
    )
    captured = capsys.readouterr()

    assert "Cache status:" in captured.out
    assert "programs: 2 days old" in captured.out
    assert "seasons/groupings: 4 days old" in captured.out
    assert "episodes: 6 days old" in captured.out
    assert "raiplaysound-cli list programs --refresh-catalog" in captured.out


def test_search_local_episodes_matches_extended_metadata_cache(tmp_path: Path) -> None:
    target_base = tmp_path / "Music" / "RaiPlaySound"
    show_dir = target_base / "profili"
    show_dir.mkdir(parents=True)
    (show_dir / ".metadata-cache.tsv").write_text(
        "ep-1\t20240101\tNA\tSpeciale Burnt Sugar\tAuthor Name | Description Text\n",
        encoding="utf-8",
    )

    results = search_local_episodes(
        "author",
        target_base=target_base,
        state_dir=tmp_path / "state",
    )

    assert results == [
        {
            "slug": "profili",
            "program_url": "https://www.raiplaysound.it/programmi/profili",
            "title": "Speciale Burnt Sugar",
            "date": "2024-01-01",
            "season": "NA",
            "group": "",
            "group_kind": "",
            "id": "ep-1",
            "url": "",
        }
    ]


def test_search_local_groupings_reads_cached_list_payloads(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "list-seasons"
    state_dir.mkdir(parents=True)
    (state_dir / "profili.json").write_text(
        json.dumps(
            {
                "slug": "profili",
                "program_url": "https://www.raiplaysound.it/programmi/profili",
                "has_seasons": False,
                "items": [
                    {
                        "key": "speciale-lucio-dalla",
                        "label": "Speciale Lucio Dalla",
                        "kind": "special",
                        "episodes": 2,
                        "published": "2024",
                        "url": "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = search_local_groupings("lucio", state_dir=tmp_path / "state")

    assert results == [
        {
            "slug": "profili",
            "program_url": "https://www.raiplaysound.it/programmi/profili",
            "label": "Speciale Lucio Dalla",
            "key": "speciale-lucio-dalla",
            "kind": "special",
            "published": "2024",
            "url": "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
            "episodes": 2,
            "all_seasons": False,
        }
    ]
