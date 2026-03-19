from __future__ import annotations

import concurrent.futures
import json
import re
import time
from pathlib import Path

from .models import Program, Station
from .runtime import http_get


def _normalize_program_excerpt(value: str) -> str:
    collapsed = " ".join(value.split())
    if not collapsed:
        return ""
    if len(collapsed) <= 120:
        return collapsed
    return f"{collapsed[:117].rstrip()}..."


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
            if len(parts) < 8:
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
    info = payload.get("podcast_info") if isinstance(payload.get("podcast_info"), dict) else {}
    title = info.get("title") or payload.get("title") or slug
    channel = info.get("channel") if isinstance(info.get("channel"), dict) else {}
    if not channel:
        channel = payload.get("channel") if isinstance(payload.get("channel"), dict) else {}
    station_name = channel.get("name") or "No station"
    station_short = (channel.get("category_path") or "none").lower()
    description_excerpt = _normalize_program_excerpt(
        str(
            info.get("description")
            or info.get("vanity")
            or payload.get("description")
            or payload.get("subtitle")
            or ""
        )
    )
    filters = payload.get("filters") if isinstance(payload.get("filters"), list) else []
    year = str(info.get("year") or payload.get("year") or "")
    create_date = str(info.get("create_date") or payload.get("create_date") or "")
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
    return Program(
        slug=slug,
        title=title,
        station_name=station_name,
        station_short=station_short,
        years=years,
        page_url=f"https://www.raiplaysound.it/programmi/{slug}",
        description_excerpt=description_excerpt,
        grouping_count=len(filters),
    )


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
            executor.submit(fetch_program_metadata, slug, years_map.get(slug, "")): slug
            for slug in slugs
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
        (
            slug,
            title,
            station_name,
            station_short,
            years,
            page_url,
            description_excerpt,
            grouping_count,
        ) = line.split("\t", 7)
        programs.append(
            Program(
                slug=slug,
                title=title,
                station_name=station_name,
                station_short=station_short,
                years=years,
                page_url=page_url,
                description_excerpt=description_excerpt,
                grouping_count=int(grouping_count or "0"),
            )
        )
    return programs


def write_program_cache(path: Path, programs: list[Program]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            f"{item.slug}\t{item.title}\t{item.station_name}\t{item.station_short}\t"
            f"{item.years}\t{item.page_url}\t{item.description_excerpt}\t"
            f"{item.grouping_count}\n"
            for item in programs
        ),
        encoding="utf-8",
    )
