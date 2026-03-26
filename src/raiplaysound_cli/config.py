from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from .errors import CLIError


def expand_config_path(value: str) -> str:
    value = value.strip()
    if value.startswith("~"):
        value = os.path.expanduser(value)
    return value.replace("${HOME}", str(Path.home())).replace("$HOME", str(Path.home()))


def normalize_bool(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
            stripped = stripped[1:-1]
        data[key.strip()] = stripped
    return data


def choose_command(argv: list[str], config: dict[str, str]) -> tuple[str, list[str]]:
    if argv and argv[0] in {"list", "search", "download"}:
        return argv[0], argv[1:]

    configured = config.get("COMMAND", "").strip().lower()
    if configured in {"list", "search", "download"}:
        return configured, argv

    list_switches = {
        "--detailed",
        "--group-by",
        "--sorted",
        "--filter",
        "--pager",
        "--refresh-catalog",
        "--catalog-max-age-hours",
        "--show-urls",
    }
    if any(arg in list_switches for arg in argv):
        return "list", argv
    return "download", argv


def _parse_int_setting(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise CLIError(f"invalid integer value for {name}: {value}") from exc


@dataclasses.dataclass(slots=True)
class Settings:
    target_base: Path = Path.home() / "Music" / "RaiPlaySound"
    audio_format: str = "m4a"
    jobs: int = 3
    metadata_max_age_hours: int = 24
    catalog_max_age_hours: int = 2160
    check_jobs: int = 8
    catalog_cache_file: Path = (
        Path.home() / ".local" / "state" / "raiplaysound-cli" / "program-catalog.tsv"
    )
    auto_redownload_missing: bool = False
    enable_log: bool = False
    debug_pids: bool = False
    log_path_arg: str = ""
    force_refresh_metadata: bool = False
    clear_metadata_cache: bool = False
    force_refresh_catalog: bool = False
    rss_feed: bool = False
    rss_base_url: str = ""
    playlist: bool = False
    input_value: str = ""
    favorites: list[str] = dataclasses.field(default_factory=list)
    list_target: str = ""
    group_by: str = "auto"
    podcasts_sorted: bool = False
    station_filter: str = ""
    stations_detailed: bool = False
    show_urls: bool = False
    pager: bool = False
    seasons_arg: str = ""
    groups_arg: str = ""
    episodes_arg: str = ""
    episode_urls_arg: str = ""

    @classmethod
    def from_config(cls, config: dict[str, str]) -> "Settings":
        settings = cls()
        for key, value in config.items():
            if key == "TARGET_BASE":
                settings.target_base = Path(expand_config_path(value))
            elif key == "AUDIO_FORMAT":
                settings.audio_format = value.lower()
            elif key == "JOBS":
                settings.jobs = _parse_int_setting(key, value)
            elif key == "METADATA_MAX_AGE_HOURS":
                settings.metadata_max_age_hours = _parse_int_setting(key, value)
            elif key == "CHECK_JOBS":
                settings.check_jobs = _parse_int_setting(key, value)
            elif key == "CATALOG_MAX_AGE_HOURS":
                settings.catalog_max_age_hours = _parse_int_setting(key, value)
            elif key == "CATALOG_CACHE_FILE":
                settings.catalog_cache_file = Path(expand_config_path(value))
            elif key in {"AUTO_REDOWNLOAD_MISSING", "DOWNLOAD_MISSING"}:
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.auto_redownload_missing = parsed
            elif key == "ENABLE_LOG":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.enable_log = parsed
            elif key == "DEBUG_PIDS":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.debug_pids = parsed
            elif key == "LOG_PATH_ARG":
                settings.log_path_arg = expand_config_path(value)
            elif key == "FORCE_REFRESH_METADATA":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.force_refresh_metadata = parsed
            elif key == "CLEAR_METADATA_CACHE":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.clear_metadata_cache = parsed
            elif key == "FORCE_REFRESH_CATALOG":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.force_refresh_catalog = parsed
            elif key == "RSS_FEED":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.rss_feed = parsed
            elif key == "RSS_BASE_URL":
                settings.rss_base_url = value.rstrip("/")
            elif key == "PLAYLIST":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.playlist = parsed
            elif key == "INPUT":
                settings.input_value = value
            elif key == "FAVORITES":
                settings.favorites = [item.strip() for item in value.split(",") if item.strip()]
            elif key == "LIST_TARGET":
                settings.list_target = value.lower()
            elif key in {"GROUP_BY", "PODCASTS_GROUP_BY"}:
                settings.group_by = value.lower()
            elif key == "PODCASTS_SORTED":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.podcasts_sorted = parsed
            elif key == "STATION_FILTER":
                settings.station_filter = value.lower()
            elif key == "STATIONS_DETAILED":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.stations_detailed = parsed
            elif key == "SHOW_URLS":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.show_urls = parsed
            elif key == "PAGER":
                parsed = normalize_bool(value)
                if parsed is not None:
                    settings.pager = parsed
            elif key == "SEASONS_ARG":
                settings.seasons_arg = value
            elif key == "GROUPS_ARG":
                settings.groups_arg = value
            elif key == "EPISODES_ARG":
                settings.episodes_arg = value
            elif key == "EPISODE_URLS_ARG":
                settings.episode_urls_arg = value
        return settings
