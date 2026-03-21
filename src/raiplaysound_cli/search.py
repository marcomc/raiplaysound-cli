from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from .catalog import (
    cache_file_is_fresh,
    collect_program_catalog,
    load_cached_programs,
    parse_stations,
    program_cache_format_is_current,
    write_program_cache,
)
from .episodes import load_metadata_cache
from .errors import CLIError
from .models import EpisodeMetadata, Program, Station
from .runtime import http_get


def normalize_query(query: str) -> str:
    return " ".join(query.split()).strip()


def query_terms(query: str) -> list[str]:
    normalized = normalize_query(query).casefold()
    return [term for term in normalized.split(" ") if term]


def matches_query(query: str, *values: str) -> bool:
    haystack = " ".join(value for value in values if value).casefold()
    terms = query_terms(query)
    return bool(terms) and all(term in haystack for term in terms)


def load_programs(
    *,
    catalog_cache_file: Path,
    refresh_catalog: bool,
    catalog_max_age_hours: int,
) -> list[Program]:
    cache_current = program_cache_format_is_current(catalog_cache_file)
    cache_ok = (
        not refresh_catalog
        and cache_current
        and cache_file_is_fresh(catalog_cache_file, catalog_max_age_hours)
    )
    if cache_ok:
        return load_cached_programs(catalog_cache_file)
    try:
        programs = collect_program_catalog()
    except CLIError:
        if cache_current and catalog_cache_file.exists():
            return load_cached_programs(catalog_cache_file)
        raise
    write_program_cache(catalog_cache_file, programs)
    return programs


def search_stations(query: str) -> list[dict[str, str]]:
    stations = parse_stations(http_get("https://www.raiplaysound.it/dirette.json"))
    matches: list[dict[str, str]] = []
    for station in stations:
        if not matches_query(
            query,
            station.name,
            station.short,
            station.page_url,
            station.feed_url,
        ):
            continue
        matches.append(_station_to_payload(station))
    return sorted(matches, key=lambda item: item["name"].casefold())


def search_programs(
    query: str,
    *,
    catalog_cache_file: Path,
    refresh_catalog: bool,
    catalog_max_age_hours: int,
) -> list[dict[str, str | int]]:
    programs = load_programs(
        catalog_cache_file=catalog_cache_file,
        refresh_catalog=refresh_catalog,
        catalog_max_age_hours=catalog_max_age_hours,
    )
    matches: list[dict[str, str | int]] = []
    for program in programs:
        if not matches_query(
            query,
            program.title,
            program.slug,
            program.station_name,
            program.station_short,
            program.years,
            program.description_excerpt,
        ):
            continue
        matches.append(_program_to_payload(program))
    return sorted(matches, key=lambda item: (str(item["title"]).casefold(), str(item["slug"])))


def search_local_groupings(query: str, *, state_dir: Path) -> list[dict[str, str | int | bool]]:
    cache_dir = state_dir / "list-seasons"
    if not cache_dir.exists():
        return []
    results: list[dict[str, str | int | bool]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = str(payload.get("slug") or "")
        program_url = str(payload.get("program_url") or "")
        has_seasons = bool(payload.get("has_seasons"))
        for raw_item in payload.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            label = str(raw_item.get("label") or "")
            key = str(raw_item.get("key") or "")
            kind = str(raw_item.get("kind") or "")
            published = str(raw_item.get("published") or "")
            url = str(raw_item.get("url") or "")
            if not matches_query(query, slug, label, key, kind, published, url):
                continue
            marker = (slug, kind, key)
            if marker in seen:
                continue
            seen.add(marker)
            results.append(
                {
                    "slug": slug,
                    "program_url": program_url,
                    "label": label,
                    "key": key,
                    "kind": kind,
                    "published": published,
                    "url": url,
                    "episodes": int(raw_item.get("episodes") or 0),
                    "all_seasons": has_seasons and kind == "season",
                }
            )
    return sorted(results, key=lambda item: (str(item["slug"]), str(item["label"]).casefold()))


def search_local_episodes(
    query: str,
    *,
    target_base: Path,
    state_dir: Path,
) -> list[dict[str, str]]:
    entries: dict[tuple[str, str], dict[str, str]] = {}
    metadata_by_slug: dict[str, dict[str, EpisodeMetadata]] = {}

    for metadata_path in sorted(target_base.glob("*/.metadata-cache.tsv")):
        slug = metadata_path.parent.name
        metadata = load_metadata_cache(metadata_path)
        metadata_by_slug[slug] = metadata
        for episode_id, item in metadata.items():
            entries[(slug, episode_id)] = {
                "slug": slug,
                "program_url": f"https://www.raiplaysound.it/programmi/{slug}",
                "episode_id": episode_id,
                "title": item.title,
                "date": _pretty_date(item.upload_date),
                "season": item.season,
                "group": "",
                "group_kind": "",
                "url": "",
                "search_text": item.search_text,
            }

    cache_dir = state_dir / "list-episodes"
    if cache_dir.exists():
        for path in sorted(cache_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            slug = str(payload.get("slug") or "")
            program_url = str(
                payload.get("program_url") or f"https://www.raiplaysound.it/programmi/{slug}"
            )
            slug_metadata = metadata_by_slug.get(slug, {})
            for raw_episode in payload.get("episodes", []):
                if not isinstance(raw_episode, dict):
                    continue
                episode_id = str(raw_episode.get("episode_id") or "")
                if not episode_id:
                    continue
                item = slug_metadata.get(episode_id, EpisodeMetadata())
                key = (slug, episode_id)
                entry = entries.setdefault(
                    key,
                    {
                        "slug": slug,
                        "program_url": program_url,
                        "episode_id": episode_id,
                        "title": "",
                        "date": "",
                        "season": "",
                        "group": "",
                        "group_kind": "",
                        "url": "",
                        "search_text": item.search_text,
                    },
                )
                entry["program_url"] = program_url
                entry["title"] = str(raw_episode.get("title") or entry["title"] or item.title)
                entry["date"] = str(raw_episode.get("upload_date") or "")
                if entry["date"]:
                    entry["date"] = _pretty_date(entry["date"])
                elif item.upload_date:
                    entry["date"] = _pretty_date(item.upload_date)
                entry["season"] = str(raw_episode.get("season") or entry["season"] or item.season)
                entry["group"] = str(raw_episode.get("group_label") or entry["group"])
                entry["group_kind"] = str(raw_episode.get("group_kind") or entry["group_kind"])
                entry["url"] = str(raw_episode.get("url") or entry["url"])
                if item.search_text and not entry["search_text"]:
                    entry["search_text"] = item.search_text

    matches: list[dict[str, str]] = []
    for entry in entries.values():
        if not matches_query(
            query,
            entry["slug"],
            entry["title"],
            entry["episode_id"],
            entry["season"],
            entry["group"],
            entry["group_kind"],
            entry["url"],
            entry["search_text"],
        ):
            continue
        matches.append(
            {
                "slug": entry["slug"],
                "program_url": entry["program_url"],
                "title": entry["title"] or entry["episode_id"],
                "date": entry["date"] or "unknown-date",
                "season": entry["season"] or "NA",
                "group": entry["group"],
                "group_kind": entry["group_kind"],
                "id": entry["episode_id"],
                "url": entry["url"],
            }
        )
    return sorted(
        matches,
        key=lambda item: (
            item["slug"],
            item["date"],
            item["title"].casefold(),
            item["id"],
        ),
        reverse=True,
    )


def search_all(
    query: str,
    *,
    target_base: Path,
    catalog_cache_file: Path,
    refresh_catalog: bool,
    catalog_max_age_hours: int,
) -> dict[str, Any]:
    state_dir = catalog_cache_file.parent
    stations: list[dict[str, str]] = []
    stations_cache_info = {"source": "live", "age": "live lookup unavailable"}
    try:
        stations = search_stations(query)
        stations_cache_info = {"source": "live", "age": "live"}
    except CLIError:
        pass

    programs: list[dict[str, str | int]] = []
    programs_cache_info = _single_cache_info(
        catalog_cache_file,
        fallback="not cached yet",
    )
    try:
        programs = search_programs(
            query,
            catalog_cache_file=catalog_cache_file,
            refresh_catalog=refresh_catalog,
            catalog_max_age_hours=catalog_max_age_hours,
        )
    except CLIError:
        if not catalog_cache_file.exists():
            programs_cache_info = {
                "source": "cache",
                "age": "live lookup unavailable and no local cache",
            }

    return {
        "query": normalize_query(query),
        "stations": stations,
        "programs": programs,
        "groupings": search_local_groupings(query, state_dir=state_dir),
        "episodes": search_local_episodes(query, target_base=target_base, state_dir=state_dir),
        "local_episode_metadata": (target_base.exists()),
        "cache_info": {
            "stations": stations_cache_info,
            "programs": programs_cache_info,
            "groupings": _multi_cache_info(
                sorted((state_dir / "list-seasons").glob("*.json")),
                fallback="no local season/grouping cache yet",
            ),
            "episodes": _multi_cache_info(
                sorted(target_base.glob("*/.metadata-cache.tsv")),
                fallback="no local episode metadata cache yet",
            ),
        },
        "refresh_hint": "raiplaysound-cli list programs --refresh-catalog",
    }


def _station_to_payload(station: Station) -> dict[str, str]:
    return {
        "name": station.name,
        "slug": station.short,
        "page_url": station.page_url,
        "feed_url": station.feed_url,
    }


def _program_to_payload(program: Program) -> dict[str, str | int]:
    return {
        "slug": program.slug,
        "title": program.title,
        "station_name": program.station_name,
        "station_short": program.station_short,
        "years": program.years,
        "page_url": program.page_url,
        "description_excerpt": program.description_excerpt,
        "grouping_count": program.grouping_count,
    }


def _pretty_date(value: str) -> str:
    normalized = value.strip()
    if len(normalized) == 8 and normalized.isdigit():
        return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"
    return normalized or "unknown-date"


def _single_cache_info(path: Path, *, fallback: str) -> dict[str, str]:
    if not path.exists():
        return {"source": "cache", "age": fallback}
    return {"source": "cache", "age": _age_text(path.stat().st_mtime)}


def _multi_cache_info(paths: list[Path], *, fallback: str) -> dict[str, str]:
    if not paths:
        return {"source": "cache", "age": fallback}
    ages = [_age_days(path.stat().st_mtime) for path in paths]
    youngest = min(ages)
    oldest = max(ages)
    if math.isclose(youngest, oldest):
        return {"source": "cache", "age": _format_age_days(oldest)}
    return {
        "source": "cache",
        "age": f"{_format_age_days(youngest)} to {_format_age_days(oldest)} old",
    }


def _age_text(mtime: float) -> str:
    return f"{_format_age_days(_age_days(mtime))} old"


def _age_days(mtime: float) -> float:
    age_seconds = max(0.0, time.time() - mtime)
    return age_seconds / 86400.0


def _format_age_days(days: float) -> str:
    if days < 1:
        return "less than 1 day"
    rounded = int(days)
    unit = "day" if rounded == 1 else "days"
    return f"{rounded} {unit}"
