from __future__ import annotations

import subprocess

from raiplaysound_cli import catalog, episodes
from raiplaysound_cli.models import Program


def test_fetch_program_metadata_parses_station_and_year(monkeypatch) -> None:
    monkeypatch.setattr(
        catalog,
        "http_get",
        lambda _url, timeout=20.0: (
            '{"title":"Show A","channel":{"name":"Radio 2","category_path":"radio2"},'
            '"year":"","create_date":"2024-05-01"}'
        ),
    )

    program = catalog.fetch_program_metadata("show-a", "2025")

    assert program == Program(
        slug="show-a",
        title="Show A",
        station_name="Radio 2",
        station_short="radio2",
        years="2024-2025",
    )


def test_discover_feed_sources_extracts_program_and_selected_season(monkeypatch) -> None:
    monkeypatch.setattr(
        episodes,
        "http_get",
        lambda _url: (
            '<a href="/programmi/america7/episodi/stagione-1">s1</a>'
            '<a href="/programmi/america7/episodi/stagione-2">s2</a>'
            '<a href="/programmi/othershow/episodi/stagione-1">ignore</a>'
        ),
    )

    sources = episodes.discover_feed_sources(
        "america7",
        {"2"},
        include_all_seasons=False,
        for_list_seasons=False,
    )

    assert sources == [
        "https://www.raiplaysound.it/programmi/america7",
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
    ]


def test_collect_episodes_from_sources_deduplicates_ids_and_assigns_season(monkeypatch) -> None:
    outputs = {
        "https://www.raiplaysound.it/programmi/america7": (
            "ep-1\thttps://www.raiplaysound.it/audio/show-ep-1.html\n"
        ),
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2": (
            "ep-1\thttps://www.raiplaysound.it/audio/show-ep-1.html\n"
            "ep-2\thttps://www.raiplaysound.it/audio/show-ep-2.html\n"
        ),
    }

    def fake_run_yt_dlp(args: list[str]) -> subprocess.CompletedProcess[str]:
        source = args[-1]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=outputs[source],
            stderr="",
        )

    monkeypatch.setattr(episodes, "run_yt_dlp", fake_run_yt_dlp)

    result = episodes.collect_episodes_from_sources(
        [
            "https://www.raiplaysound.it/programmi/america7",
            "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
        ]
    )

    assert [episode.episode_id for episode in result] == ["ep-1", "ep-2"]
    assert result[0].season == "1"
    assert result[1].season == "2"
