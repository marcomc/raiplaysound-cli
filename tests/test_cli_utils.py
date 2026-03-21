from pathlib import Path

from raiplaysound_cli.catalog import (
    cache_file_is_fresh,
    load_cached_programs,
    program_cache_format_is_current,
)
from raiplaysound_cli.config import (
    Settings,
    expand_config_path,
    normalize_bool,
    parse_env_file,
)
from raiplaysound_cli.episodes import (
    build_requested_episode_filters,
    build_requested_groups,
    build_requested_set,
    cache_entry_is_complete,
    infer_season_from_text,
    load_metadata_cache,
    normalize_episode_metadata,
    normalize_season_key,
    year_span,
)
from raiplaysound_cli.errors import CLIError
from raiplaysound_cli.models import Episode, EpisodeMetadata
from raiplaysound_cli.runtime import acquire_lock, release_lock


def test_expand_config_path_home() -> None:
    assert expand_config_path("~/Music").endswith("/Music")
    assert str(Path.home()) in expand_config_path("$HOME/Music")


def test_normalize_bool_variants() -> None:
    assert normalize_bool("true") is True
    assert normalize_bool("OFF") is False
    assert normalize_bool("maybe") is None


def test_parse_env_file(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        'AUDIO_FORMAT="mp3"\n# comment\nJOBS=5\nGROUPS_ARG="speciali,battiti"\n',
        encoding="utf-8",
    )
    parsed = parse_env_file(config)
    assert parsed["AUDIO_FORMAT"] == "mp3"
    assert parsed["JOBS"] == "5"
    settings = Settings.from_config(parsed)
    assert settings.audio_format == "mp3"
    assert settings.jobs == 5
    assert settings.groups_arg == "speciali,battiti"


def test_requested_seasons() -> None:
    selected, all_flag = build_requested_set("1,2")
    assert selected == {"1", "2"}
    assert all_flag is False
    selected, all_flag = build_requested_set("2025")
    assert selected == {"2025"}
    assert all_flag is False
    selected, all_flag = build_requested_set("2024-2025")
    assert selected == {"2024-2025"}
    assert all_flag is False
    selected, all_flag = build_requested_set("all")
    assert selected == set()
    assert all_flag is True


def test_requested_episode_filters() -> None:
    ids, urls = build_requested_episode_filters(
        "abc123",
        "https://www.raiplaysound.it/audio/foo-12345678-abcd-1234-abcd-1234567890ab.html",
    )
    assert ids == {"abc123"}
    assert list(urls.values()) == ["12345678-abcd-1234-abcd-1234567890ab"]


def test_requested_groups() -> None:
    selected = build_requested_groups("speciali, Speciale Lucio Dalla")
    assert selected == {"speciali", "speciale-lucio-dalla"}


def test_infer_season_from_text() -> None:
    assert infer_season_from_text("My Show S2E13 title") == "2"
    assert infer_season_from_text("No season here") is None


def test_normalize_season_key_supports_year_ranges_and_ordinals() -> None:
    assert normalize_season_key("2025/2026") == "2025-2026"
    assert normalize_season_key("Stagione 2025-2026") == "2025-2026"
    assert normalize_season_key("seconda-stagione") == "2"


def test_normalize_episode_metadata() -> None:
    episodes = [
        Episode(episode_id="a", url="https://example.com/2024/01/a", label="a"),
        Episode(episode_id="b", url="https://example.com/2025/01/b", label="b", season="2"),
    ]
    summary = normalize_episode_metadata(
        episodes,
        {
            "a": EpisodeMetadata(upload_date="20240101", season="1", title="Episode A"),
            "b": EpisodeMetadata(upload_date="20250101", season="2", title="Episode B"),
        },
    )
    assert summary.has_seasons is True
    assert summary.latest_season == "2"
    assert episodes[0].pretty_date == "2024-01-01"
    assert year_span(summary.show_year_min, summary.show_year_max) == "2024-2025"


def test_normalize_episode_metadata_preserves_year_range_seasons() -> None:
    episodes = [
        Episode(
            episode_id="a",
            url="https://example.com/2025/10/a",
            label="a",
            season="2024-2025",
        ),
        Episode(
            episode_id="b",
            url="https://example.com/2026/02/b",
            label="b",
            season="2025-2026",
        ),
    ]
    summary = normalize_episode_metadata(
        episodes,
        {
            "a": EpisodeMetadata(
                upload_date="20251001",
                season="2024-2025",
                title="Episode A",
            ),
            "b": EpisodeMetadata(
                upload_date="20260201",
                season="2025/2026",
                title="Episode B",
            ),
        },
    )
    assert summary.has_seasons is True
    assert summary.latest_season == "2025-2026"
    assert summary.counts == {"2024-2025": 1, "2025-2026": 1}
    assert episodes[1].season == "2025-2026"


def test_program_cache_format_is_current(tmp_path: Path) -> None:
    current = tmp_path / "current.tsv"
    current.write_text(
        "slug\ttitle\tNo station\tnone\t2024\thttps://example.com/programmi/slug\tExcerpt\t2\t2\n",
        encoding="utf-8",
    )
    assert program_cache_format_is_current(current) is True
    legacy = tmp_path / "legacy.tsv"
    legacy.write_text(
        "slug\ttitle\tNo station\tnone\t2024\thttps://example.com/programmi/slug\tExcerpt\t2\n",
        encoding="utf-8",
    )
    assert program_cache_format_is_current(legacy) is False


def test_load_cached_programs_skips_malformed_rows(tmp_path: Path) -> None:
    cache = tmp_path / "program-catalog.tsv"
    cache.write_text(
        "broken-row\n"
        "slug\ttitle\tNo station\tnone\t2024\thttps://example.com/programmi/slug\tExcerpt\tx\t2\n",
        encoding="utf-8",
    )
    programs = load_cached_programs(cache)
    assert len(programs) == 1
    assert programs[0].grouping_count == 0


def test_cache_file_is_fresh(tmp_path: Path) -> None:
    cache = tmp_path / "cache.tsv"
    cache.write_text("x\n", encoding="utf-8")
    assert cache_file_is_fresh(cache, 1) is True


def test_cache_entry_is_complete() -> None:
    assert (
        cache_entry_is_complete(
            EpisodeMetadata(upload_date="20240101", season="1", title="Episode A")
        )
        is True
    )
    assert (
        cache_entry_is_complete(EpisodeMetadata(upload_date="NA", season="1", title="Episode A"))
        is False
    )
    assert (
        cache_entry_is_complete(EpisodeMetadata(upload_date="20240101", season="1", title="NA"))
        is False
    )
    assert cache_entry_is_complete(None) is False


def test_load_metadata_cache_skips_malformed_rows(tmp_path: Path) -> None:
    cache = tmp_path / ".metadata-cache.tsv"
    cache.write_text(
        "broken-row\nepisode-1\t20240101\t1\tEpisode Title\n",
        encoding="utf-8",
    )
    metadata = load_metadata_cache(cache)
    assert metadata == {
        "episode-1": EpisodeMetadata(
            upload_date="20240101",
            season="1",
            title="Episode Title",
            search_text="",
        )
    }


def test_load_metadata_cache_accepts_legacy_and_extended_rows(tmp_path: Path) -> None:
    cache = tmp_path / ".metadata-cache.tsv"
    cache.write_text(
        (
            "legacy\t20240101\t1\tLegacy Episode\n"
            "extended\t20240202\t2\tExtended Episode\tAuthor Name | Description\n"
        ),
        encoding="utf-8",
    )

    result = load_metadata_cache(cache)

    assert result["legacy"] == EpisodeMetadata(
        upload_date="20240101",
        season="1",
        title="Legacy Episode",
        search_text="",
    )
    assert result["extended"] == EpisodeMetadata(
        upload_date="20240202",
        season="2",
        title="Extended Episode",
        search_text="Author Name | Description",
    )


def test_invalid_integer_setting_raises_cli_error() -> None:
    try:
        Settings.from_config({"JOBS": "abc"})
    except CLIError as exc:
        assert "invalid integer value for JOBS" in str(exc)
    else:
        raise AssertionError("expected CLIError")


def test_acquire_lock_recovers_stale_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / ".run-lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text("999999\n", encoding="utf-8")
    acquire_lock(lock_dir, "america7")
    try:
        assert (lock_dir / "pid").read_text(encoding="utf-8").strip().isdigit()
    finally:
        release_lock(lock_dir)
