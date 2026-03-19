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


def test_discover_season_listing_sources_prefers_season_pages(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/america7":
            return (
                '<a href="/programmi/america7/episodi/stagione-1">s1</a>'
                '<a href="/programmi/america7/episodi/stagione-2">s2</a>'
            )
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    program_url, sources = episodes.discover_season_listing_sources("america7")

    assert program_url == "https://www.raiplaysound.it/programmi/america7"
    assert sources == [
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-1",
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
    ]


def test_discover_season_listing_sources_probes_unlinked_next_season(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/america7":
            return '<a href="/programmi/america7/episodi/stagione-1">s1</a>'
        if url == "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2":
            return "<title>America7 | Stagione 2</title>"
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    program_url, sources = episodes.discover_season_listing_sources("america7")

    assert program_url == "https://www.raiplaysound.it/programmi/america7"
    assert sources == [
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-1",
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
    ]


def test_discover_season_listing_supports_puntate_and_text_current(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/leripetizioni":
            return (
                '<li class="filter-checked text-gray-dark"> Stagione 5 </li>'
                '<a href="/programmi/leripetizioni/puntate/stagione-4">Stagione 4</a>'
                '<a href="/programmi/leripetizioni/puntate/stagione-3">Stagione 3</a>'
                '<a href="/programmi/leripetizioni/puntate/stagione-2">Stagione 2</a>'
                '<a href="/programmi/leripetizioni/puntate/stagione-1">Stagione 1</a>'
            )
        if url == "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-5":
            return "<title>Le ripetizioni | Stagione 5</title>"
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    program_url, sources = episodes.discover_season_listing_sources("leripetizioni")

    assert program_url == "https://www.raiplaysound.it/programmi/leripetizioni"
    assert sources == [
        "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-1",
        "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-2",
        "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-3",
        "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-4",
        "https://www.raiplaysound.it/programmi/leripetizioni/puntate/stagione-5",
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

    def fake_run_yt_dlp(
        args: list[str], *, allow_partial_failure: bool = False
    ) -> subprocess.CompletedProcess[str]:
        assert allow_partial_failure is True
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
    assert result[0].season == "2"
    assert result[1].season == "2"


def test_collect_episodes_from_sources_uses_ignore_errors_for_broken_items(monkeypatch) -> None:
    captured_args: list[list[str]] = []

    def fake_run_yt_dlp(
        args: list[str], *, allow_partial_failure: bool = False
    ) -> subprocess.CompletedProcess[str]:
        assert allow_partial_failure is True
        captured_args.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="ep-1\thttps://www.raiplaysound.it/audio/show-ep-1.html\n",
            stderr="",
        )

    monkeypatch.setattr(episodes, "run_yt_dlp", fake_run_yt_dlp)

    result = episodes.collect_episodes_from_sources(
        ["https://www.raiplaysound.it/programmi/battiti/puntate/speciali"]
    )

    assert [episode.episode_id for episode in result] == ["ep-1"]
    assert captured_args == [
        [
            "--flat-playlist",
            "--ignore-errors",
            "--print",
            "%(id)s\t%(webpage_url)s",
            "https://www.raiplaysound.it/programmi/battiti/puntate/speciali",
        ]
    ]


def test_collect_metadata_accepts_partial_failure_output(monkeypatch) -> None:
    def fake_run_yt_dlp(
        args: list[str], *, allow_partial_failure: bool = False
    ) -> subprocess.CompletedProcess[str]:
        assert allow_partial_failure is True
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=(
                "ep-1\t20240101\tEpisode One\tNA\n"
                "ERROR: broken item\n"
                "ep-2\t20240102\tEpisode Two\t2\n"
            ),
            stderr="ERROR: broken item",
        )

    monkeypatch.setattr(episodes, "run_yt_dlp", fake_run_yt_dlp)

    result = episodes.collect_metadata(["https://www.raiplaysound.it/programmi/battiti"])

    assert result == {
        "ep-1": ("20240101", "NA", "Episode One"),
        "ep-2": ("20240102", "2", "Episode Two"),
    }


def test_collect_metadata_uses_no_playlist_for_single_entries(monkeypatch) -> None:
    captured_args: list[list[str]] = []

    def fake_run_yt_dlp(
        args: list[str], *, allow_partial_failure: bool = False
    ) -> subprocess.CompletedProcess[str]:
        assert allow_partial_failure is True
        captured_args.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="ep-1\t20240101\tEpisode One\tNA\n",
            stderr="",
        )

    monkeypatch.setattr(episodes, "run_yt_dlp", fake_run_yt_dlp)

    result = episodes.collect_metadata(
        ["https://www.raiplaysound.it/audio/2024/01/episode-one-ep-1.json"],
        single_entries=True,
    )

    assert result == {"ep-1": ("20240101", "NA", "Episode One")}
    assert captured_args == [
        [
            "--skip-download",
            "--ignore-errors",
            "--print",
            "%(id)s\t%(upload_date|NA)s\t%(title|NA)s\t%(season_number|NA)s",
            "--no-playlist",
            "https://www.raiplaysound.it/audio/2024/01/episode-one-ep-1.json",
        ]
    ]


def test_collect_metadata_uses_episode_json_for_single_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        episodes,
        "http_get",
        lambda url: (
            '{"uniquename":"ContentItem-48e8407b-360f-472f-969e-a1c2f24e713c",'
            '"date_tracking":"2022-03-09","title":"Speciale Burnt Sugar",'
            '"season":"2021-22","path_id":"/audio/2022/03/Speciale-Burnt-Sugar-'
            '48e8407b-360f-472f-969e-a1c2f24e713c.json"}'
        ),
    )
    monkeypatch.setattr(
        episodes,
        "run_yt_dlp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("yt-dlp should not run")),
    )

    result = episodes.collect_metadata(
        [
            "https://www.raiplaysound.it/audio/2022/03/Speciale-Burnt-Sugar-48e8407b-360f-472f-969e-a1c2f24e713c.html"
        ],
        single_entries=True,
    )

    assert result == {
        "48e8407b-360f-472f-969e-a1c2f24e713c": (
            "20220309",
            "2021-22",
            "Speciale Burnt Sugar",
        )
    }


def test_collect_season_summary_from_sources_uses_url_years_without_metadata(monkeypatch) -> None:
    outputs = {
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-1": (
            "ep-1\thttps://www.raiplaysound.it/audio/2024/05/show-ep-1.html\n"
        ),
        "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2": (
            "ep-2\thttps://www.raiplaysound.it/audio/2025/02/show-ep-2.html\n"
            "ep-3\thttps://www.raiplaysound.it/audio/2026/03/show-ep-3.html\n"
        ),
    }

    def fake_run_yt_dlp(
        args: list[str], *, allow_partial_failure: bool = False
    ) -> subprocess.CompletedProcess[str]:
        assert allow_partial_failure is True
        source = args[-1]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=outputs[source],
            stderr="",
        )

    monkeypatch.setattr(episodes, "run_yt_dlp", fake_run_yt_dlp)

    result, summary = episodes.collect_season_summary_from_sources(
        [
            "https://www.raiplaysound.it/programmi/america7/episodi/stagione-1",
            "https://www.raiplaysound.it/programmi/america7/episodi/stagione-2",
        ]
    )

    assert [episode.year for episode in result] == ["2024", "2025", "2026"]
    assert summary.has_seasons is True
    assert summary.counts == {"1": 1, "2": 2}
    assert summary.year_min == {"1": "2024", "2": "2025"}
    assert summary.year_max == {"1": "2024", "2": "2026"}
    assert summary.show_year_min == "2024"
    assert summary.show_year_max == "2026"


def test_discover_group_listing_sources_supports_speciali(monkeypatch) -> None:
    monkeypatch.setattr(
        episodes,
        "http_get",
        lambda _url: (
            "<button data-filters-current><span>Speciale Pino Daniele</span></button>"
            '<a href="/programmi/profili/speciali/speciale-lucio-dalla">Speciale Lucio Dalla</a>'
        ),
    )

    program_url, groups = episodes.discover_group_listing_sources("profili")

    assert program_url == "https://www.raiplaysound.it/programmi/profili"
    assert [(group.label, group.kind, group.url) for group in groups] == [
        (
            "Speciale Pino Daniele",
            "special",
            "https://www.raiplaysound.it/programmi/profili",
        ),
        (
            "Speciale Lucio Dalla",
            "special",
            "https://www.raiplaysound.it/programmi/profili/speciali/speciale-lucio-dalla",
        ),
    ]


def test_discover_group_listing_sources_supports_year_and_series_buckets(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/wikiradio":
            return (
                "<button data-filters-current><span>2026</span></button>"
                '<a href="/programmi/wikiradio/episodi-/2025">2025</a>'
            )
        if url == "https://www.raiplaysound.it/programmi/3sullaluna":
            return (
                '<a href="/programmi/3sullaluna/puntate-e-podcast/destinazione-luna">'
                "Destinazione Luna</a>"
            )
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    _program_url, groups = episodes.discover_group_listing_sources("wikiradio")

    assert [(group.label, group.kind, group.url) for group in groups] == [
        ("2026", "bucket", "https://www.raiplaysound.it/programmi/wikiradio"),
        ("2025", "bucket", "https://www.raiplaysound.it/programmi/wikiradio/episodi-/2025"),
    ]

    _program_url, groups = episodes.discover_group_listing_sources("3sullaluna")

    assert [(group.label, group.kind, group.url) for group in groups] == [
        (
            "Destinazione Luna",
            "series",
            "https://www.raiplaysound.it/programmi/3sullaluna/puntate-e-podcast/destinazione-luna",
        )
    ]


def test_discover_group_listing_sources_skips_auxiliary_tabs(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/show":
            return (
                '<a href="/programmi/show/clip">Clip</a>'
                '<a href="/programmi/show/extra">Extra</a>'
                '<a href="/programmi/show/playlist">Playlist</a>'
                '<a href="/programmi/show/novita">Novita</a>'
            )
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    _program_url, groups = episodes.discover_group_listing_sources("show")

    assert groups == []


def test_discover_season_listing_sources_supports_caret_current_labels(monkeypatch) -> None:
    def fake_http_get(url: str) -> str:
        if url == "https://www.raiplaysound.it/programmi/afroamerica-blackmusicrevolution":
            return (
                "<button data-filters-current><span>2^ Stagione</span></button>"
                '<a href="/programmi/afroamerica-blackmusicrevolution/episodi/episodi">Episodi</a>'
            )
        if url == (
            "https://www.raiplaysound.it/programmi/"
            "afroamerica-blackmusicrevolution/episodi/stagione-1"
        ):
            return "<title>Afroamerica | Stagione 1</title>"
        if url == (
            "https://www.raiplaysound.it/programmi/"
            "afroamerica-blackmusicrevolution/episodi/stagione-2"
        ):
            return "<title>Afroamerica | Stagione 2</title>"
        raise RuntimeError("not found")

    monkeypatch.setattr(episodes, "http_get", fake_http_get)

    program_url, sources = episodes.discover_season_listing_sources(
        "afroamerica-blackmusicrevolution"
    )

    assert program_url == "https://www.raiplaysound.it/programmi/afroamerica-blackmusicrevolution"
    assert sources == [
        "https://www.raiplaysound.it/programmi/afroamerica-blackmusicrevolution/episodi/stagione-1",
        "https://www.raiplaysound.it/programmi/afroamerica-blackmusicrevolution/episodi/stagione-2",
    ]
