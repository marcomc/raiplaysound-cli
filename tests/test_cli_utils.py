from pathlib import Path

from raiplaysound_cli.cli import (
    Settings,
    build_requested_episode_filters,
    build_requested_set,
    cache_file_is_fresh,
    expand_config_path,
    infer_season_from_text,
    normalize_bool,
    normalize_episode_metadata,
    parse_env_file,
    program_cache_format_is_current,
    year_span,
    Episode,
)


def test_expand_config_path_home() -> None:
    assert expand_config_path("~/Music").endswith("/Music")
    assert str(Path.home()) in expand_config_path("$HOME/Music")


def test_normalize_bool_variants() -> None:
    assert normalize_bool("true") is True
    assert normalize_bool("OFF") is False
    assert normalize_bool("maybe") is None


def test_parse_env_file(tmp_path: Path) -> None:
    config = tmp_path / "config.env"
    config.write_text('AUDIO_FORMAT="mp3"\n# comment\nJOBS=5\n', encoding="utf-8")
    parsed = parse_env_file(config)
    assert parsed["AUDIO_FORMAT"] == "mp3"
    assert parsed["JOBS"] == "5"
    settings = Settings.from_config(parsed)
    assert settings.audio_format == "mp3"
    assert settings.jobs == 5


def test_requested_seasons() -> None:
    selected, all_flag = build_requested_set("1,2")
    assert selected == {"1", "2"}
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


def test_infer_season_from_text() -> None:
    assert infer_season_from_text("My Show S2E13 title") == "2"
    assert infer_season_from_text("No season here") is None


def test_normalize_episode_metadata() -> None:
    episodes = [
        Episode(episode_id="a", url="https://example.com/2024/01/a", label="a"),
        Episode(episode_id="b", url="https://example.com/2025/01/b", label="b", season="2"),
    ]
    summary = normalize_episode_metadata(
        episodes,
        {
            "a": ("20240101", "1", "Episode A"),
            "b": ("20250101", "2", "Episode B"),
        },
    )
    assert summary.has_seasons is True
    assert summary.latest_season == "2"
    assert episodes[0].pretty_date == "2024-01-01"
    assert year_span(summary.show_year_min, summary.show_year_max) == "2024-2025"


def test_program_cache_format_is_current(tmp_path: Path) -> None:
    current = tmp_path / "current.tsv"
    current.write_text("slug\ttitle\tNo station\tnone\t2024\n", encoding="utf-8")
    assert program_cache_format_is_current(current) is True
    legacy = tmp_path / "legacy.tsv"
    legacy.write_text("slug\ttitle\tNo station\tunknown\t2024\n", encoding="utf-8")
    assert program_cache_format_is_current(legacy) is False


def test_cache_file_is_fresh(tmp_path: Path) -> None:
    cache = tmp_path / "cache.tsv"
    cache.write_text("x\n", encoding="utf-8")
    assert cache_file_is_fresh(cache, 1) is True
