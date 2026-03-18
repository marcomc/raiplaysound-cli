from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import dataclasses
import email.utils
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from . import __version__

console = Console()
err_console = Console(stderr=True)

PROGRAM_URL_RE = re.compile(r"^https?://www\.raiplaysound\.it/programmi/([A-Za-z0-9-]+)/?$")
PROGRAM_SLUG_RE = re.compile(r"^[A-Za-z0-9-]+$")
EPISODE_URL_RE = re.compile(r"^https?://www\.raiplaysound\.it/.+")
SEASON_PAGE_RE = re.compile(rf"/programmi/(?P<slug>[A-Za-z0-9-]+)/episodi/stagione-(?P<season>\d+)")
DATE_IN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
EPISODE_ID_FROM_URL_RE = re.compile(r"-([0-9a-fA-F-]{8,})\.(?:html|json)$")
SEASON_IN_TITLE_RE = re.compile(r"[Ss](\d{1,3})[ _-]*[Ee]\d{1,3}")


class CLIError(Exception):
    pass


def expand_config_path(value: str) -> str:
    value = value.strip()
    if value.startswith("~"):
        value = os.path.expanduser(value)
    value = value.replace("${HOME}", str(Path.home())).replace("$HOME", str(Path.home()))
    return value


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
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def json_dump(data: Any) -> None:
    console.print(json.dumps(data, indent=2, ensure_ascii=False))


def http_get(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "raiplaysound-cli/2.0",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def run_yt_dlp(args: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["yt-dlp", *args]
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise CLIError("yt-dlp is required but was not found in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or f"yt-dlp failed with exit code {exc.returncode}"
        raise CLIError(detail) from exc


def detect_slug(input_value: str) -> tuple[str, str]:
    match = PROGRAM_URL_RE.match(input_value)
    if match:
        slug = match.group(1).lower()
        return slug, f"https://www.raiplaysound.it/programmi/{slug}"
    if PROGRAM_SLUG_RE.match(input_value):
        slug = input_value.lower()
        return slug, f"https://www.raiplaysound.it/programmi/{slug}"
    raise CLIError(
        "input must be a RaiPlaySound program slug (for example musicalbox) or a full program URL."
    )


def choose_command(argv: list[str], config: dict[str, str]) -> tuple[str, list[str]]:
    if argv and argv[0] in {"list", "download"}:
        return argv[0], argv[1:]

    configured = config.get("COMMAND", "").strip().lower()
    if configured in {"list", "download"}:
        return configured, argv

    list_switches = {
        "--stations",
        "--programs",
        "--seasons",
        "--episodes",
        "--detailed",
        "--group-by",
        "--sorted",
        "--filter",
        "--refresh-catalog",
        "--catalog-max-age-hours",
        "--show-urls",
    }
    if any(arg in list_switches for arg in argv):
        return "list", argv
    return "download", argv


@dataclasses.dataclass(slots=True)
class Settings:
    target_base: Path = Path.home() / "Music" / "RaiPlaySound"
    audio_format: str = "m4a"
    jobs: int = 3
    metadata_max_age_hours: int = 24
    catalog_max_age_hours: int = 2160
    check_jobs: int = 8
    catalog_cache_file: Path = Path.home() / ".local" / "state" / "raiplaysound-cli" / "program-catalog.tsv"
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
    list_target: str = ""
    group_by: str = "auto"
    podcasts_sorted: bool = False
    station_filter: str = ""
    stations_detailed: bool = False
    show_urls: bool = False
    seasons_arg: str = ""
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
                settings.jobs = int(value)
            elif key == "METADATA_MAX_AGE_HOURS":
                settings.metadata_max_age_hours = int(value)
            elif key == "CHECK_JOBS":
                settings.check_jobs = int(value)
            elif key == "CATALOG_MAX_AGE_HOURS":
                settings.catalog_max_age_hours = int(value)
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
            elif key == "SEASONS_ARG":
                settings.seasons_arg = value
            elif key == "EPISODES_ARG":
                settings.episodes_arg = value
            elif key == "EPISODE_URLS_ARG":
                settings.episode_urls_arg = value
        return settings


@dataclasses.dataclass(slots=True)
class Program:
    slug: str
    title: str
    station_name: str
    station_short: str
    years: str


@dataclasses.dataclass(slots=True)
class Station:
    short: str
    name: str
    page_url: str
    feed_url: str


@dataclasses.dataclass(slots=True)
class Episode:
    episode_id: str
    url: str
    label: str
    title: str = ""
    upload_date: str = "NA"
    season: str = "1"
    year: str = "NA"

    @property
    def pretty_date(self) -> str:
        if re.fullmatch(r"\d{8}", self.upload_date):
            return f"{self.upload_date[:4]}-{self.upload_date[4:6]}-{self.upload_date[6:8]}"
        return "unknown-date"


def parse_stations(raw_json: str) -> list[Station]:
    payload = json.loads(raw_json)
    if isinstance(payload, dict):
        items = payload.get("contents") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    stations: list[Station] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get("weblink", "")
        short = link.strip("/").split("/", 1)[0] or "unknown"
        if short in seen:
            continue
        seen.add(short)
        stations.append(
            Station(
                short=short,
                name=item.get("title", short),
                page_url=f"https://www.raiplaysound.it{link}",
                feed_url=f"https://www.raiplaysound.it{item.get('path_id', '')}",
            )
        )
    return stations


def cache_file_is_fresh(path: Path, max_age_hours: int) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return 0 <= age_seconds <= max_age_hours * 3600


def program_cache_format_is_current(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                return False
            if parts[2] == "No station" and parts[3].lower() != "none":
                return False
        return True
    except OSError:
        return False


def build_program_last_year_map() -> dict[str, str]:
    xml_text = http_get("https://www.raiplaysound.it/sitemap.archivio.programmi.xml")
    matches = re.findall(
        r"https://www\.raiplaysound\.it/sitemap\.programmi\.([^<]+)\.xml</loc>\s*<lastmod>(\d{4})-",
        xml_text,
    )
    result: dict[str, str] = {}
    for slug, year in matches:
        result.setdefault(slug, year)
    return result


def fetch_program_metadata(slug: str, last_year: str = "") -> Program | None:
    try:
        raw = http_get(f"https://www.raiplaysound.it/programmi/{slug}.json", timeout=20.0)
    except Exception:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    title = payload.get("title") or slug
    channel = payload.get("channel") or {}
    station_name = channel.get("name") or "No station"
    station_short = (channel.get("category_path") or "none").lower()
    year = str(payload.get("year") or "")
    create_date = str(payload.get("create_date") or "")
    if not re.fullmatch(r"\d{4}", year):
        match = re.search(r"(\d{4})", create_date)
        year = match.group(1) if match else ""
    years = "unknown"
    if re.fullmatch(r"\d{4}", year) and re.fullmatch(r"\d{4}", last_year):
        start_year = min(year, last_year)
        years = start_year if start_year == last_year else f"{start_year}-{last_year}"
    elif re.fullmatch(r"\d{4}", year):
        years = year
    elif re.fullmatch(r"\d{4}", last_year):
        years = last_year
    return Program(slug=slug, title=title, station_name=station_name, station_short=station_short, years=years)


def collect_program_catalog() -> list[Program]:
    sitemap_index = http_get("https://www.raiplaysound.it/sitemap.archivio.programmi.xml")
    slugs = sorted(
        set(
            re.findall(
                r"https://www\.raiplaysound\.it/sitemap\.programmi\.([^<]+)\.xml",
                sitemap_index,
            )
        )
    )
    years_map = build_program_last_year_map()
    programs: list[Program] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_map = {
            executor.submit(fetch_program_metadata, slug, years_map.get(slug, "")): slug for slug in slugs
        }
        for future in concurrent.futures.as_completed(future_map):
            program = future.result()
            if program is not None:
                programs.append(program)
    programs.sort(key=lambda item: item.slug)
    return programs


def collect_station_program_catalog(station_short: str) -> list[Program]:
    raw = http_get(f"https://www.raiplaysound.it/{station_short}.json")
    slugs = sorted(set(re.findall(r"/programmi/([A-Za-z0-9-]+)", raw)))
    if not slugs:
        raise CLIError(f"unable to find programs for station slug '{station_short}'.")
    years_map = build_program_last_year_map()
    programs: list[Program] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        future_map = {
            executor.submit(fetch_program_metadata, slug, years_map.get(slug, "")): slug for slug in slugs
        }
        for future in concurrent.futures.as_completed(future_map):
            program = future.result()
            if program is not None:
                programs.append(program)
    programs.sort(key=lambda item: item.slug)
    return programs


def load_cached_programs(path: Path) -> list[Program]:
    programs: list[Program] = []
    if not path.exists():
        return programs
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        slug, title, station_name, station_short, years = line.split("\t", 4)
        programs.append(Program(slug=slug, title=title, station_name=station_name, station_short=station_short, years=years))
    return programs


def write_program_cache(path: Path, programs: list[Program]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            f"{item.slug}\t{item.title}\t{item.station_name}\t{item.station_short}\t{item.years}\n"
            for item in programs
        ),
        encoding="utf-8",
    )


def fetch_program_page(slug: str) -> str:
    return http_get(f"https://www.raiplaysound.it/programmi/{slug}")


def discover_feed_sources(slug: str, selected_seasons: set[str], include_all_seasons: bool, for_list_seasons: bool) -> list[str]:
    program_url = f"https://www.raiplaysound.it/programmi/{slug}"
    html = fetch_program_page(slug)
    season_urls = sorted(
        {
            f"https://www.raiplaysound.it{match.group(0)}"
            for match in SEASON_PAGE_RE.finditer(html)
            if match.group("slug").lower() == slug.lower()
        }
    )
    if not season_urls:
        return [program_url]
    if selected_seasons and not include_all_seasons and not for_list_seasons:
        filtered = [url for url in season_urls if url.rsplit("-", 1)[-1] in selected_seasons]
        return sorted(set(filtered + [program_url]))
    return sorted(set(season_urls + [program_url]))


def collect_episodes_from_sources(sources: list[str]) -> list[Episode]:
    seen: set[str] = set()
    episodes: list[Episode] = []
    for source in sources:
        season_hint = ""
        match = re.search(r"stagione-(\d+)$", source)
        if match:
            season_hint = match.group(1)
        result = run_yt_dlp(["--flat-playlist", "--print", "%(id)s\t%(webpage_url)s", source])
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            episode_id = parts[0].strip()
            episode_url = parts[1].strip().rstrip("/")
            if not episode_id or not episode_url or episode_id in seen:
                continue
            seen.add(episode_id)
            base_name = Path(urllib.parse.urlparse(episode_url).path).stem
            label = re.sub(rf"-{re.escape(episode_id)}$", "", base_name) or episode_id
            episodes.append(Episode(episode_id=episode_id, url=episode_url, label=label, season=season_hint or "1"))
    if not episodes:
        raise CLIError("No episodes found.")
    return episodes


def load_metadata_cache(path: Path) -> dict[str, tuple[str, str, str]]:
    cache: dict[str, tuple[str, str, str]] = {}
    if not path.exists():
        return cache
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        episode_id, upload, season, title = line.split("\t", 3)
        cache[episode_id] = (upload, season, title)
    return cache


def write_metadata_cache(path: Path, cache: dict[str, tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for episode_id in sorted(cache):
        upload, season, title = cache[episode_id]
        safe_title = title.replace("\t", " ").replace("\n", " ")
        lines.append(f"{episode_id}\t{upload}\t{season}\t{safe_title}\n")
    path.write_text("".join(lines), encoding="utf-8")


def collect_metadata(sources: list[str]) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for source in sources:
        metadata = run_yt_dlp(
            ["--skip-download", "--ignore-errors", "--print", "%(id)s\t%(upload_date|NA)s\t%(title|NA)s\t%(season_number|NA)s", source]
        )
        for line in metadata.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            episode_id, upload_date, title, season = parts[0], parts[1], parts[2], parts[3]
            result.setdefault(episode_id, (upload_date, season, title))
    return result


def infer_season_from_text(text: str) -> str | None:
    match = SEASON_IN_TITLE_RE.search(text)
    if match:
        return match.group(1)
    return None


def extract_year_from_url(url: str) -> str:
    match = re.search(r"/(\d{4})/(\d{2})/", url)
    return match.group(1) if match else "NA"


@dataclasses.dataclass(slots=True)
class SeasonSummary:
    counts: dict[str, int]
    year_min: dict[str, str]
    year_max: dict[str, str]
    show_year_min: str
    show_year_max: str
    has_seasons: bool
    latest_season: str


def normalize_episode_metadata(episodes: list[Episode], metadata: dict[str, tuple[str, str, str]]) -> SeasonSummary:
    season_counts: dict[str, int] = {}
    season_year_min: dict[str, str] = {}
    season_year_max: dict[str, str] = {}
    show_year_min = ""
    show_year_max = ""
    detected_season_evidence = False
    for episode in episodes:
        upload_date, meta_season, title = metadata.get(episode.episode_id, ("NA", "NA", episode.label.replace("-", " ")))
        episode.title = title if title and title != "NA" else episode.label.replace("-", " ")
        episode.upload_date = upload_date or "NA"
        season_candidate = "NA"
        if meta_season.isdigit():
            season_candidate = meta_season
            detected_season_evidence = True
        elif episode.season.isdigit():
            season_candidate = episode.season
            detected_season_evidence = True
        else:
            inferred = infer_season_from_text(episode.title)
            if inferred:
                season_candidate = inferred
                detected_season_evidence = True
        if not season_candidate.isdigit():
            season_candidate = "1"
        episode.season = season_candidate
        episode.year = episode.upload_date[:4] if re.fullmatch(r"\d{8}", episode.upload_date) else extract_year_from_url(episode.url)
        season_counts[season_candidate] = season_counts.get(season_candidate, 0) + 1
        if re.fullmatch(r"\d{4}", episode.year):
            if not show_year_min or episode.year < show_year_min:
                show_year_min = episode.year
            if not show_year_max or episode.year > show_year_max:
                show_year_max = episode.year
            current_min = season_year_min.get(season_candidate)
            current_max = season_year_max.get(season_candidate)
            if current_min is None or episode.year < current_min:
                season_year_min[season_candidate] = episode.year
            if current_max is None or episode.year > current_max:
                season_year_max[season_candidate] = episode.year
    latest_season = sorted(season_counts, key=lambda value: int(value))[-1] if season_counts else "1"
    has_seasons = detected_season_evidence or len(season_counts) > 1
    return SeasonSummary(
        counts=season_counts,
        year_min=season_year_min,
        year_max=season_year_max,
        show_year_min=show_year_min,
        show_year_max=show_year_max,
        has_seasons=has_seasons,
        latest_season=latest_season,
    )


def year_span(min_year: str, max_year: str) -> str:
    if re.fullmatch(r"\d{4}", min_year) and re.fullmatch(r"\d{4}", max_year):
        return min_year if min_year == max_year else f"{min_year}-{max_year}"
    if re.fullmatch(r"\d{4}", min_year):
        return min_year
    if re.fullmatch(r"\d{4}", max_year):
        return max_year
    return "unknown year"


def build_output_template(has_seasons: bool, target_dir: Path) -> str:
    if has_seasons:
        return str(target_dir / "%(series,playlist_title,uploader)s - S%(season_number|0)02d%(episode_number|0)02d - %(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s")
    return str(target_dir / "%(series,playlist_title,uploader)s - %(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s")


def build_requested_set(raw: str) -> tuple[set[str], bool]:
    selected: set[str] = set()
    request_all = False
    if not raw:
        return selected, request_all
    for part in [item.strip() for item in raw.split(",") if item.strip()]:
        if part.lower() == "all":
            return set(), True
        if not part.isdigit() or not 1 <= int(part) <= 100:
            raise CLIError(f"invalid season '{part}'. Allowed values are 1-100 or 'all'.")
        selected.add(part)
    return selected, request_all


def build_requested_episode_filters(ids_raw: str, urls_raw: str) -> tuple[set[str], dict[str, str]]:
    ids: set[str] = set()
    urls: dict[str, str] = {}
    if ids_raw:
        for part in [item.strip() for item in ids_raw.split(",") if item.strip()]:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
                raise CLIError(f"invalid episode ID '{part}'.")
            ids.add(part)
    if urls_raw:
        for part in [item.strip() for item in urls_raw.split(",") if item.strip()]:
            if not EPISODE_URL_RE.match(part):
                raise CLIError(f"invalid episode URL '{part}'.")
            normalized = part.rstrip("/")
            match = EPISODE_ID_FROM_URL_RE.search(normalized)
            urls[normalized] = match.group(1) if match else ""
    return ids, urls


def filter_episodes_for_list_or_download(
    episodes: list[Episode],
    summary: SeasonSummary,
    selected_seasons: set[str],
    request_all_seasons: bool,
    requested_episode_ids: set[str],
    requested_episode_urls: dict[str, str],
    latest_by_default: bool,
) -> list[Episode]:
    selected = episodes
    if summary.has_seasons:
        if request_all_seasons:
            pass
        elif selected_seasons:
            available = {episode.season for episode in episodes}
            missing = sorted(selected_seasons - available, key=int)
            if missing:
                raise CLIError(f"season {missing[0]} is not available.")
            selected = [episode for episode in selected if episode.season in selected_seasons]
        elif latest_by_default and not requested_episode_ids and not requested_episode_urls:
            selected = [episode for episode in selected if episode.season == summary.latest_season]
    elif selected_seasons:
        raise CLIError("this program does not expose seasons, so --season cannot be used.")

    if requested_episode_ids or requested_episode_urls:
        matched_ids: set[str] = set()
        matched_urls: set[str] = set()
        filtered: list[Episode] = []
        for episode in selected:
            include = False
            if episode.episode_id in requested_episode_ids:
                include = True
                matched_ids.add(episode.episode_id)
            normalized = episode.url.rstrip("/")
            if normalized in requested_episode_urls:
                include = True
                matched_urls.add(normalized)
            for requested_url, extracted_id in requested_episode_urls.items():
                if extracted_id and extracted_id == episode.episode_id:
                    include = True
                    matched_urls.add(requested_url)
            if include:
                filtered.append(episode)
        missing_ids = sorted(requested_episode_ids - matched_ids)
        if missing_ids:
            raise CLIError(f"episode ID '{missing_ids[0]}' not found.")
        missing_urls = sorted(set(requested_episode_urls) - matched_urls)
        if missing_urls:
            raise CLIError(f"episode URL not found: {missing_urls[0]}")
        selected = filtered
    return selected


def fetch_show_title(slug: str) -> str:
    program = fetch_program_metadata(slug)
    return program.title if program else slug


def media_type_for_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg; codecs=opus",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".wav": "audio/wav",
    }.get(suffix, "audio/mpeg")


def generate_rss_feed(target_dir: Path, slug: str, program_url: str, metadata_cache_file: Path, base_url: str) -> Path:
    cache_by_date: dict[str, tuple[str, str]] = {}
    for episode_id, (upload, _season, title) in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", upload):
            cache_by_date.setdefault(f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}", (title, episode_id))
    show_title = fetch_show_title(slug)
    items = []
    for file_path in sorted(target_dir.iterdir(), reverse=True):
        if not file_path.is_file():
            continue
        match = DATE_IN_NAME_RE.search(file_path.name)
        if not match:
            continue
        file_date = match.group(1)
        if file_date in cache_by_date:
            title, guid = cache_by_date[file_date]
        else:
            title = re.sub(r"^.*\d{4}-\d{2}-\d{2}\s+-\s+", "", file_path.stem)
            guid = file_path.stem
        if base_url:
            enclosure = f"{base_url.rstrip('/')}/{slug}/{urllib.parse.quote(file_path.name)}"
        else:
            enclosure = file_path.resolve().as_uri()
        items.append(
            {
                "title": title,
                "guid": guid,
                "pub_date": email.utils.formatdate(time.mktime(time.strptime(file_date, "%Y-%m-%d")), usegmt=True),
                "enclosure": enclosure,
                "size": str(file_path.stat().st_size),
                "mime": media_type_for_suffix(file_path),
            }
        )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        "  <channel>",
        f"    <title>{xml_escape(show_title)}</title>",
        f"    <link>{xml_escape(program_url)}</link>",
        f"    <description>{xml_escape(show_title)}</description>",
        "    <language>it</language>",
        f"    <itunes:title>{xml_escape(show_title)}</itunes:title>",
        "    <itunes:author>RAI Play Sound</itunes:author>",
        "    <itunes:explicit>false</itunes:explicit>",
    ]
    for item in items:
        lines.extend(
            [
                "    <item>",
                f"      <title>{xml_escape(item['title'])}</title>",
                f"      <link>{xml_escape(program_url)}</link>",
                f"      <guid isPermaLink=\"false\">{xml_escape(item['guid'])}</guid>",
                f"      <pubDate>{item['pub_date']}</pubDate>",
                f"      <enclosure url=\"{xml_escape(item['enclosure'])}\" length=\"{item['size']}\" type=\"{xml_escape(item['mime'])}\"/>",
                "    </item>",
            ]
        )
    lines.extend(["  </channel>", "</rss>"])
    feed_path = target_dir / "feed.xml"
    feed_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return feed_path


def generate_playlist(target_dir: Path, metadata_cache_file: Path) -> Path:
    cache_by_date: dict[str, str] = {}
    for _episode_id, (upload, _season, title) in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", upload):
            cache_by_date.setdefault(f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}", title)
    entries: list[tuple[str, Path]] = []
    for file_path in target_dir.iterdir():
        if file_path.is_file():
            match = DATE_IN_NAME_RE.search(file_path.name)
            if match:
                entries.append((match.group(1), file_path))
    entries.sort(key=lambda item: item[0])
    lines = ["#EXTM3U"]
    for file_date, file_path in entries:
        title = cache_by_date.get(file_date) or re.sub(r"^.*\d{4}-\d{2}-\d{2}\s+-\s+", "", file_path.stem)
        lines.append(f"#EXTINF:-1,{title}")
        lines.append(file_path.name)
    playlist_path = target_dir / "playlist.m3u"
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist_path


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclasses.dataclass(slots=True)
class DownloadTask:
    episode: Episode
    task_id: TaskID


class Downloader:
    def __init__(
        self,
        *,
        archive_file: Path,
        output_template: str,
        audio_format: str,
        log_file: Path | None,
        rich_progress: Progress,
        overall_task_id: TaskID,
        debug_pids: bool,
    ) -> None:
        self.archive_file = archive_file
        self.output_template = output_template
        self.audio_format = audio_format
        self.log_file = log_file
        self.progress = rich_progress
        self.overall_task_id = overall_task_id
        self.debug_pids = debug_pids
        self.lock = threading.Lock()
        self.processes: set[subprocess.Popen[str]] = set()

    def log(self, message: str) -> None:
        if self.log_file is not None:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")

    def terminate_all(self) -> None:
        with self.lock:
            for process in list(self.processes):
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()

    def download_one(self, episode: Episode, task_id: TaskID) -> tuple[str, str]:
        cmd = [
            "yt-dlp",
            "--format",
            "bestaudio/best",
            "--parse-metadata",
            r"title:^(?P<series>.+?) S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$",
            "--download-archive",
            str(self.archive_file),
            "--no-overwrites",
            "--ignore-errors",
            "--extract-audio",
            "--audio-format",
            self.audio_format,
            "--audio-quality",
            "0",
            "--add-metadata",
            "--embed-thumbnail",
            "--newline",
            "--progress",
            "--progress-template",
            "progress:%(progress.downloaded_bytes|0)d:%(progress.total_bytes|0)d:%(progress.total_bytes_estimate|0)d:%(progress._percent_str)s",
            "-o",
            self.output_template,
            episode.url,
        ]
        if self.log_file is not None:
            cmd.insert(-2, "--verbose")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        with self.lock:
            self.processes.add(process)
        if self.debug_pids:
            self.log(f"[pid] episode={episode.episode_id} pid={process.pid}")
        state = "DONE"
        detail = "done"
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if self.log_file is not None and not line.startswith("progress:"):
                self.log(line)
            if "has already been recorded in the archive" in line:
                state = "SKIP"
                detail = "downloaded"
                self.progress.update(task_id, description=f"skip {episode.label}", completed=100, total=100)
                continue
            if line.startswith("ERROR:"):
                state = "ERROR"
                detail = "error"
                self.progress.update(task_id, description=f"error {episode.label}", completed=100, total=100)
                continue
            if not line.startswith("progress:"):
                continue
            _, downloaded_s, total_s, estimate_s, raw_percent = line.split(":", 4)
            downloaded = int(downloaded_s) if downloaded_s.isdigit() else 0
            total = int(total_s) if total_s.isdigit() else 0
            estimate = int(estimate_s) if estimate_s.isdigit() else 0
            if total > 0:
                self.progress.update(task_id, total=total, completed=downloaded)
            elif estimate > 0:
                self.progress.update(task_id, total=estimate, completed=downloaded)
            percent_text = raw_percent.strip().replace("%", "")
            if total == 0 and estimate == 0 and percent_text:
                try:
                    percent = min(int(float(percent_text)), 100)
                    self.progress.update(task_id, completed=percent, total=100)
                except ValueError:
                    pass
        process.wait()
        with self.lock:
            self.processes.discard(process)
        if process.returncode != 0 and state != "SKIP":
            state = "ERROR"
            detail = f"yt-dlp exit code {process.returncode}"
        self.progress.remove_task(task_id)
        return state, detail


def print_programs_text(programs: list[Program], mode: str) -> None:
    if mode == "sorted":
        console.print(f"Programs sorted alphabetically ({len(programs)}):")
        for program in sorted(programs, key=lambda item: (item.title.casefold(), item.slug)):
            console.print(f"  - {program.title} ({program.slug}) [{program.years}]")
        return
    if mode == "alpha":
        console.print(f"Programs grouped alphabetically ({len(programs)}):")
        current_group = None
        for program in sorted(programs, key=lambda item: (item.title.casefold(), item.slug)):
            group = program.title[:1].upper()
            if not group.isalpha():
                group = "#"
            if group != current_group:
                current_group = group
                console.print("")
                console.print(f"[{group}]")
            console.print(f"  - {program.title} ({program.slug}) [{program.station_name}:{program.station_short} | {program.years}]")
        return
    console.print(f"Programs grouped by station ({len(programs)}):")
    current_station = None
    for program in sorted(programs, key=lambda item: (item.station_name.casefold(), item.title.casefold(), item.slug)):
        station_key = (program.station_name, program.station_short)
        if station_key != current_station:
            current_station = station_key
            console.print("")
            console.print(f"[{program.station_name} | {program.station_short}]")
        console.print(f"  - {program.title} ({program.slug}) [{program.years}]")


def list_stations(settings: Settings, args: argparse.Namespace) -> int:
    stations = parse_stations(http_get("https://www.raiplaysound.it/dirette.json"))
    if args.json:
        json_dump(
            {
                "mode": "stations",
                "count": len(stations),
                "detailed": args.detailed,
                "stations": [dataclasses.asdict(item) for item in stations],
            }
        )
        return 0
    console.print(
        "Available RaiPlaySound radio stations (detailed):"
        if args.detailed
        else "Available RaiPlaySound radio stations (station slug -> name):"
    )
    for station in stations:
        console.print(f"  - {station.short:<16} {station.name}")
        if args.detailed:
            console.print(f"      page: {station.page_url}")
            console.print(f"      feed: {station.feed_url}")
    return 0


def list_programs(settings: Settings, args: argparse.Namespace) -> int:
    station_filter = (args.filter or settings.station_filter or "").lower()
    cache_ok = (
        not args.refresh_catalog
        and program_cache_format_is_current(settings.catalog_cache_file)
        and cache_file_is_fresh(settings.catalog_cache_file, args.catalog_max_age_hours)
    )
    if cache_ok:
        programs = load_cached_programs(settings.catalog_cache_file)
    else:
        programs = collect_program_catalog()
        write_program_cache(settings.catalog_cache_file, programs)
    if station_filter:
        programs = [program for program in programs if program.station_short == station_filter]
        if not programs:
            raise CLIError(f"No programs found for station slug '{station_filter}'.")
    mode = "sorted" if args.sorted else ("alpha" if (args.group_by == "alpha" or (args.group_by == "auto" and station_filter)) else "station")
    if args.json:
        json_dump(
            {
                "mode": "programs",
                "count": len(programs),
                "grouping": mode,
                "station_filter": station_filter,
                "programs": [dataclasses.asdict(item) for item in programs],
            }
        )
        return 0
    print_programs_text(programs, mode)
    return 0


def load_show_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    for_list_seasons: bool = False,
) -> tuple[str, str, list[Episode], SeasonSummary, Path]:
    slug, program_url = detect_slug(input_value)
    target_dir = settings.target_base / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    sources = discover_feed_sources(slug, selected_seasons, request_all_seasons, for_list_seasons)
    episodes = collect_episodes_from_sources(sources)
    cache = {}
    if not settings.force_refresh_metadata and cache_file_is_fresh(metadata_cache_file, settings.metadata_max_age_hours):
        cache = load_metadata_cache(metadata_cache_file)
    need_refresh = any(episode.episode_id not in cache or not cache[episode.episode_id][1:] for episode in episodes)
    if settings.force_refresh_metadata or need_refresh:
        cache.update(collect_metadata(sources))
        write_metadata_cache(metadata_cache_file, cache)
    summary = normalize_episode_metadata(episodes, cache)
    return slug, program_url, episodes, summary, metadata_cache_file


def list_seasons(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    slug, program_url, episodes, summary, _metadata_cache = load_show_context(
        settings,
        args.input,
        selected_seasons,
        request_all,
        for_list_seasons=True,
    )
    if args.json:
        seasons = []
        if not summary.has_seasons:
            seasons.append({"season": "1", "episodes": len(episodes), "published": year_span(summary.show_year_min, summary.show_year_max)})
        else:
            for season in sorted(summary.counts, key=lambda item: int(item)):
                seasons.append(
                    {
                        "season": season,
                        "episodes": summary.counts[season],
                        "published": year_span(summary.year_min.get(season, ""), summary.year_max.get(season, "")),
                    }
                )
        json_dump(
            {
                "mode": "seasons",
                "slug": slug,
                "program_url": program_url,
                "has_seasons": summary.has_seasons,
                "total_episodes": len(episodes),
                "seasons": seasons,
            }
        )
        return 0
    if not summary.has_seasons:
        console.print(f"No seasons detected for {slug} ({program_url}).")
        console.print(f"  - Episodes: {len(episodes)} (published: {year_span(summary.show_year_min, summary.show_year_max)})")
        return 0
    console.print(f"Available seasons for {slug} ({program_url}):")
    for season in sorted(summary.counts, key=lambda item: int(item)):
        console.print(
            f"  - Season {season}: {summary.counts[season]} episodes (published: {year_span(summary.year_min.get(season, ''), summary.year_max.get(season, ''))})"
        )
    return 0


def list_episodes(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    slug, program_url, episodes, summary, _metadata_cache = load_show_context(settings, args.input, selected_seasons, request_all)
    filtered = filter_episodes_for_list_or_download(
        episodes,
        summary,
        selected_seasons,
        request_all,
        set(),
        {},
        latest_by_default=True,
    )
    if args.json:
        json_dump(
            {
                "mode": "episodes",
                "slug": slug,
                "program_url": program_url,
                "has_seasons": summary.has_seasons,
                "show_urls": args.show_urls,
                "episodes": [
                    {
                        "season": episode.season,
                        "date": episode.pretty_date,
                        "title": episode.title,
                        "id": episode.episode_id,
                        "url": episode.url,
                    }
                    for episode in filtered
                ],
            }
        )
        return 0
    table = Table(show_header=True)
    if summary.has_seasons:
        table.add_column("Season")
    table.add_column("Date")
    table.add_column("Episode")
    table.add_column("ID")
    if args.show_urls:
        table.add_column("URL")
    for episode in filtered:
        row = []
        if summary.has_seasons:
            row.append(f"S{episode.season}")
        row.extend([episode.pretty_date, episode.title, episode.episode_id])
        if args.show_urls:
            row.append(episode.url)
        table.add_row(*row)
    console.print(f"Episodes for {slug} ({program_url}):")
    console.print(table)
    return 0


def resolve_log_file(settings: Settings, target_dir: Path, slug: str) -> Path | None:
    if not (settings.enable_log or settings.debug_pids):
        return None
    run_ts = time.strftime("%Y%m%d-%H%M%S")
    raw = settings.log_path_arg
    if not raw:
        path = target_dir / f"{slug}-run-{run_ts}.log"
    else:
        candidate = Path(raw)
        if candidate.exists() and candidate.is_dir():
            path = candidate / f"{slug}-run-{run_ts}.log"
        elif raw.endswith("/"):
            candidate.mkdir(parents=True, exist_ok=True)
            path = candidate / f"{slug}-run-{run_ts}.log"
        else:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            path = candidate
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def predicted_media_exists(episode_url: str, output_template: str, audio_format: str) -> bool:
    try:
        result = run_yt_dlp(
            [
                "--skip-download",
                "--parse-metadata",
                r"title:^(?P<series>.+?) S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$",
                "--print",
                "filename",
                "-o",
                output_template,
                episode_url,
            ]
        )
    except CLIError:
        return False
    resolved = result.stdout.splitlines()[0].strip() if result.stdout.strip() else ""
    if not resolved:
        return False
    base = str(Path(resolved).with_suffix(""))
    for ext in [audio_format, "mp3", "m4a", "aac", "ogg", "opus", "flac", "wav", "mp4", "webm", "m4b"]:
        if Path(f"{base}.{ext}").exists():
            return True
    return False


def remove_missing_ids_from_archive(archive_file: Path, missing_ids: set[str]) -> None:
    if not archive_file.exists():
        return
    kept = []
    for line in archive_file.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and parts[1] in missing_ids:
            continue
        kept.append(line)
    archive_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def download_command(settings: Settings, args: argparse.Namespace) -> int:
    slug, program_url = detect_slug(args.input or settings.input_value)
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    requested_episode_ids, requested_episode_urls = build_requested_episode_filters(
        args.episode_ids or settings.episodes_arg,
        ",".join(args.episode_url or []) + ("," if args.episode_url and (args.episode_urls or settings.episode_urls_arg) else "") + (args.episode_urls or settings.episode_urls_arg),
    )
    target_dir = settings.target_base / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_file = target_dir / ".download-archive.txt"
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    if settings.clear_metadata_cache and metadata_cache_file.exists():
        metadata_cache_file.unlink()
    slug, program_url, episodes, summary, metadata_cache_file = load_show_context(settings, args.input or settings.input_value, selected_seasons, request_all)
    filtered = filter_episodes_for_list_or_download(
        episodes,
        summary,
        selected_seasons,
        request_all,
        requested_episode_ids,
        requested_episode_urls,
        latest_by_default=True,
    )
    if not filtered:
        raise CLIError("No episodes selected for download.")
    output_template = build_output_template(summary.has_seasons, target_dir)
    if archive_file.exists():
        archived_ids = {
            parts[1]
            for parts in (line.split(maxsplit=2) for line in archive_file.read_text(encoding="utf-8").splitlines())
            if len(parts) >= 2
        }
    else:
        archived_ids = set()
    missing_archived_ids: set[str] = set()
    if archived_ids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.check_jobs) as executor:
            future_map = {
                executor.submit(predicted_media_exists, episode.url, output_template, settings.audio_format): episode
                for episode in filtered
                if episode.episode_id in archived_ids
            }
            for future in concurrent.futures.as_completed(future_map):
                if not future.result():
                    missing_archived_ids.add(future_map[future].episode_id)
        if missing_archived_ids and settings.auto_redownload_missing:
            remove_missing_ids_from_archive(archive_file, missing_archived_ids)
    log_file = resolve_log_file(settings, target_dir, slug)
    lock_dir = target_dir / ".run-lock"
    lock_pid_file = lock_dir / "pid"
    try:
        lock_dir.mkdir()
        lock_pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except FileExistsError as exc:
        raise CLIError(f"another download process is already running for program slug '{slug}'.") from exc
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    downloader: Downloader | None = None
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        with progress:
            overall = progress.add_task(
                f"[bold]Total ({len(filtered)} episode(s))[/bold]",
                total=len(filtered),
            )
            downloader = Downloader(
                archive_file=archive_file,
                output_template=output_template,
                audio_format=settings.audio_format,
                log_file=log_file,
                rich_progress=progress,
                overall_task_id=overall,
                debug_pids=settings.debug_pids,
            )

            def _handle_signal(signum: int, _frame: Any) -> None:
                if downloader is not None:
                    downloader.terminate_all()
                raise KeyboardInterrupt(f"signal {signum}")

            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
            tasks: list[DownloadTask] = []
            for episode in filtered:
                task_id = progress.add_task(f"download {episode.label}", total=100)
                tasks.append(DownloadTask(episode=episode, task_id=task_id))
            done_count = skip_count = error_count = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=settings.jobs) as executor:
                future_map = {
                    executor.submit(downloader.download_one, item.episode, item.task_id): item.episode for item in tasks
                }
                for future in concurrent.futures.as_completed(future_map):
                    state, _detail = future.result()
                    progress.advance(overall, 1)
                    if state == "DONE":
                        done_count += 1
                    elif state == "SKIP":
                        skip_count += 1
                    else:
                        error_count += 1
            console.print(f"Completed: done={done_count}, skipped={skip_count}, errors={error_count}")
            if error_count:
                return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        shutil.rmtree(lock_dir, ignore_errors=True)
    if settings.rss_feed:
        generate_rss_feed(target_dir, slug, program_url, metadata_cache_file, settings.rss_base_url)
    if settings.playlist:
        generate_playlist(target_dir, metadata_cache_file)
    return 0


def build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raiplaysound-cli list")
    parser.add_argument("positional_a", nargs="?")
    parser.add_argument("positional_b", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--stations", action="store_true")
    parser.add_argument("--programs", action="store_true")
    parser.add_argument("--seasons", action="store_true")
    parser.add_argument("--episodes", action="store_true")
    parser.add_argument("--detailed", action="store_true")
    parser.add_argument("--group-by", choices=["auto", "alpha", "station"], default="auto")
    parser.add_argument("--filter", default="")
    parser.add_argument("--sorted", action="store_true")
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--catalog-max-age-hours", type=int, default=2160)
    parser.add_argument("--show-urls", action="store_true")
    parser.add_argument("--season", default="")
    return parser


def build_download_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="raiplaysound-cli download")
    parser.add_argument("input", nargs="?")
    parser.add_argument("-f", "--format", default=None)
    parser.add_argument("-j", "--jobs", type=int, default=None)
    parser.add_argument("-s", "--season", default="")
    parser.add_argument("--seasons", dest="season_alias", default="")
    parser.add_argument("--episode-ids", default="")
    parser.add_argument("--episodes", dest="episodes_legacy", default="")
    parser.add_argument("--episode-url", action="append", default=[])
    parser.add_argument("--episode-urls", default="")
    parser.add_argument("-m", "--missing", action="store_true")
    parser.add_argument("--log", nargs="?", const="__enable__", default=None)
    parser.add_argument("--debug-pids", action="store_true")
    parser.add_argument("--refresh-metadata", action="store_true")
    parser.add_argument("--clear-metadata-cache", action="store_true")
    parser.add_argument("--metadata-max-age-hours", type=int, default=None)
    parser.add_argument("--rss", dest="rss", action="store_true")
    parser.add_argument("--no-rss", dest="rss", action="store_false")
    parser.set_defaults(rss=None)
    parser.add_argument("--rss-base-url", default=None)
    parser.add_argument("--playlist", dest="playlist", action="store_true")
    parser.add_argument("--no-playlist", dest="playlist", action="store_false")
    parser.set_defaults(playlist=None)
    return parser


def apply_download_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    updated = dataclasses.replace(settings)
    if args.format:
        updated.audio_format = args.format.lower()
    if args.jobs:
        updated.jobs = args.jobs
    if args.missing:
        updated.auto_redownload_missing = True
    if args.log is not None:
        updated.enable_log = True
        updated.log_path_arg = "" if args.log == "__enable__" else args.log
    if args.debug_pids:
        updated.debug_pids = True
    if args.refresh_metadata:
        updated.force_refresh_metadata = True
    if args.clear_metadata_cache:
        updated.clear_metadata_cache = True
    if args.metadata_max_age_hours is not None:
        updated.metadata_max_age_hours = args.metadata_max_age_hours
    if args.rss is not None:
        updated.rss_feed = args.rss
    if args.rss_base_url is not None:
        updated.rss_base_url = args.rss_base_url.rstrip("/")
    if args.playlist is not None:
        updated.playlist = args.playlist
    if args.season_alias and not args.season:
        args.season = args.season_alias
    if args.episodes_legacy and not args.episode_ids:
        args.episode_ids = args.episodes_legacy
    return updated


def apply_list_defaults(settings: Settings, args: argparse.Namespace) -> argparse.Namespace:
    if settings.list_target and not any([args.stations, args.programs, args.seasons, args.episodes]):
        if settings.list_target == "stations":
            args.stations = True
        elif settings.list_target == "programs":
            args.programs = True
        elif settings.list_target == "seasons":
            args.seasons = True
        elif settings.list_target == "episodes":
            args.episodes = True
    if settings.show_urls and not args.show_urls:
        args.show_urls = True
    if settings.stations_detailed and not args.detailed:
        args.detailed = True
    if not args.filter and settings.station_filter:
        args.filter = settings.station_filter
    if args.group_by == "auto" and settings.group_by != "auto":
        args.group_by = settings.group_by
    if not args.sorted and settings.podcasts_sorted:
        args.sorted = True
    return args

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = []
    if "--version" in argv:
        console.print(f"raiplaysound-cli {__version__}")
        return 0
    if "-h" in argv or "--help" in argv:
        command, rest = choose_command([arg for arg in argv if arg not in {"-h", "--help"}], parse_env_file(Path.home() / ".raiplaysound-cli.conf"))
        parser = build_list_parser() if command == "list" else build_download_parser()
        parser.print_help()
        return 0
    config = parse_env_file(Path.home() / ".raiplaysound-cli.conf")
    if not config:
        legacy = Path.home() / ".raiplaysound-downloader.conf"
        if legacy.exists():
            config = parse_env_file(legacy)
    settings = Settings.from_config(config)
    command, rest = choose_command(argv, config)
    try:
        if command == "list":
            args = apply_list_defaults(settings, build_list_parser().parse_args(rest))
            target = ""
            input_value = args.positional_a
            if args.positional_a in {"stations", "programs", "seasons", "episodes"}:
                target = args.positional_a
                input_value = args.positional_b
            else:
                target = "stations" if args.stations else "programs" if args.programs else "seasons" if args.seasons else "episodes" if args.episodes else ""
            if target == "stations":
                args.stations = True
            elif target == "programs":
                args.programs = True
            elif target == "seasons":
                args.seasons = True
            elif target == "episodes":
                args.episodes = True
            args.input = input_value
            targets = sum([args.stations, args.programs, args.seasons, args.episodes])
            if targets != 1:
                raise CLIError("list mode requires exactly one target: --stations, --programs, --seasons, or --episodes.")
            if args.stations:
                return list_stations(settings, args)
            if args.programs:
                return list_programs(settings, args)
            if args.seasons:
                if not args.input:
                    raise CLIError("list seasons requires <program_slug|program_url>.")
                return list_seasons(settings, args)
            if not args.input:
                raise CLIError("list episodes requires <program_slug|program_url>.")
            return list_episodes(settings, args)
        args = build_download_parser().parse_args(rest)
        if not (args.input or settings.input_value):
            raise CLIError("download requires <program_slug|program_url>.")
        settings = apply_download_overrides(settings, args)
        if settings.audio_format not in {"mp3", "m4a", "aac", "ogg", "opus", "flac", "wav"}:
            raise CLIError(f"unsupported format '{settings.audio_format}'.")
        return download_command(settings, args)
    except CLIError as exc:
        err_console.print(f"Error: {exc}")
        return 1
