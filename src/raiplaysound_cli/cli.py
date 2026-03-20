from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import json
import shutil
import signal
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from . import __version__
from .catalog import (
    cache_file_is_fresh,
    collect_program_catalog,
    load_cached_programs,
    parse_stations,
    program_cache_format_is_current,
    write_program_cache,
)
from .config import Settings, choose_command, parse_env_file
from .downloads import (
    Downloader,
    DownloadTask,
    remove_missing_ids_from_archive,
    resolve_log_file,
)
from .episodes import (
    build_requested_episode_filters,
    build_requested_groups,
    build_requested_set,
    cache_entry_is_complete,
    collect_episodes_from_sources,
    collect_group_summaries,
    collect_metadata,
    collect_season_summary_from_sources,
    detect_slug,
    discover_feed_sources,
    discover_group_listing_sources,
    discover_grouped_episode_sources,
    discover_season_listing_sources,
    filter_episodes_for_list_or_download,
    load_metadata_cache,
    normalize_episode_metadata,
    season_sort_key,
    write_metadata_cache,
    year_span,
)
from .errors import CLIError
from .models import Episode, GroupSource, SeasonSummary
from .outputs import generate_playlist, generate_rss_feed
from .runtime import acquire_lock, http_get, release_lock, run_yt_dlp

console = Console()
err_console = Console(stderr=True)
LIST_CACHE_MAX_AGE_HOURS = 24
LIST_CACHE_VERSION = 5


def json_dump(data: Any) -> None:
    console.print(json.dumps(data, indent=2, ensure_ascii=False))


def _state_cache_dir(settings: Settings) -> Path:
    return settings.catalog_cache_file.parent


def _write_json_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json_cache(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _season_summary_cache_file(settings: Settings, slug: str) -> Path:
    return _state_cache_dir(settings) / "list-seasons" / f"{slug}.json"


def _episode_list_cache_file(settings: Settings, slug: str, sources: list[str]) -> Path:
    digest = hashlib.sha1("\n".join(sorted(sources)).encode("utf-8")).hexdigest()[:12]
    return _state_cache_dir(settings) / "list-episodes" / f"{slug}-{digest}.json"


def _episode_listing_cache_sources(
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    sources_override: list[str] | None,
    source_groups_override: list[GroupSource] | None,
) -> tuple[str, str, list[str]]:
    slug, program_url, sources, _source_groups = _resolve_episode_sources(
        input_value,
        selected_seasons,
        request_all_seasons,
        for_list_seasons=False,
        sources_override=sources_override,
        source_groups_override=source_groups_override,
    )
    return slug, program_url, sources


def _season_summary_items_to_payload(
    *,
    slug: str,
    program_url: str,
    has_seasons: bool,
    has_groups: bool,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": LIST_CACHE_VERSION,
        "slug": slug,
        "program_url": program_url,
        "has_seasons": has_seasons,
        "has_groups": has_groups,
        "items": items,
    }


def _build_season_listing_payload(settings: Settings, slug: str) -> dict[str, Any]:
    program_url, groups = discover_group_listing_sources(slug)
    if groups:
        group_summaries = collect_group_summaries(groups)
        all_seasons = all(group.kind == "season" for group in group_summaries)
        items = [
            {
                "key": group.key,
                "label": group.label if not all_seasons else f"Season {group.key}",
                "kind": group.kind,
                "episodes": group.episodes,
                "published": year_span(group.year_min, group.year_max),
                "url": group.url,
            }
            for group in group_summaries
        ]
        return _season_summary_items_to_payload(
            slug=slug,
            program_url=program_url,
            has_seasons=all_seasons,
            has_groups=True,
            items=items,
        )
    _, sources = discover_season_listing_sources(slug)
    episodes, summary = collect_season_summary_from_sources(sources)
    season_urls = {
        source.rsplit("-", 1)[-1]: source
        for source in sources
        if "/stagione-" in source and source.rsplit("-", 1)[-1].isdigit()
    }
    if not summary.has_seasons:
        items = [
            {
                "key": "default",
                "label": "All episodes",
                "kind": "flat",
                "episodes": len(episodes),
                "published": year_span(summary.show_year_min, summary.show_year_max),
                "url": program_url,
            }
        ]
    else:
        items = [
            {
                "key": season,
                "label": f"Season {season}",
                "kind": "season",
                "episodes": summary.counts[season],
                "published": year_span(
                    summary.year_min.get(season, ""),
                    summary.year_max.get(season, ""),
                ),
                "url": season_urls.get(season, f"{program_url}/stagione-{season}"),
            }
            for season in sorted(summary.counts, key=season_sort_key)
        ]
    return _season_summary_items_to_payload(
        slug=slug,
        program_url=program_url,
        has_seasons=summary.has_seasons,
        has_groups=False,
        items=items,
    )


def load_season_listing_payload(settings: Settings, slug: str) -> dict[str, Any]:
    cache_file = _season_summary_cache_file(settings, slug)
    if cache_file_is_fresh(cache_file, LIST_CACHE_MAX_AGE_HOURS):
        try:
            payload = _load_json_cache(cache_file)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            payload = {}
        if payload.get("version") == LIST_CACHE_VERSION:
            return payload
    payload = _build_season_listing_payload(settings, slug)
    _write_json_cache(cache_file, payload)
    return payload


def _episode_payload_from_context(
    slug: str,
    program_url: str,
    summary: SeasonSummary,
    episodes: list[Episode],
) -> dict[str, Any]:
    return {
        "version": LIST_CACHE_VERSION,
        "slug": slug,
        "program_url": program_url,
        "summary": {
            "has_seasons": summary.has_seasons,
            "latest_season": getattr(summary, "latest_season", "1"),
            "show_year_min": getattr(summary, "show_year_min", ""),
            "show_year_max": getattr(summary, "show_year_max", ""),
            "counts": getattr(summary, "counts", {}),
            "year_min": getattr(summary, "year_min", {}),
            "year_max": getattr(summary, "year_max", {}),
        },
        "episodes": [
            {
                "episode_id": episode.episode_id,
                "url": episode.url,
                "label": getattr(episode, "label", getattr(episode, "episode_id", "")),
                "title": getattr(episode, "title", ""),
                "upload_date": getattr(episode, "upload_date", "NA"),
                "season": getattr(episode, "season", "1"),
                "year": getattr(episode, "year", "NA"),
                "group_label": getattr(episode, "group_label", ""),
                "group_kind": getattr(episode, "group_kind", ""),
            }
            for episode in episodes
        ],
    }


def _context_from_episode_payload(
    payload: dict[str, Any],
) -> tuple[str, str, list[Episode], SeasonSummary]:
    episodes = [
        Episode(
            episode_id=item["episode_id"],
            url=item["url"],
            label=item["label"],
            title=item.get("title", ""),
            upload_date=item.get("upload_date", "NA"),
            season=item.get("season", "1"),
            year=item.get("year", "NA"),
            group_label=item.get("group_label", ""),
            group_kind=item.get("group_kind", ""),
        )
        for item in payload["episodes"]
    ]
    raw_summary = payload["summary"]
    summary = SeasonSummary(
        counts={str(key): int(value) for key, value in raw_summary["counts"].items()},
        year_min={str(key): str(value) for key, value in raw_summary["year_min"].items()},
        year_max={str(key): str(value) for key, value in raw_summary["year_max"].items()},
        show_year_min=str(raw_summary["show_year_min"]),
        show_year_max=str(raw_summary["show_year_max"]),
        has_seasons=bool(raw_summary["has_seasons"]),
        latest_season=str(raw_summary["latest_season"]),
    )
    return str(payload["slug"]), str(payload["program_url"]), episodes, summary


def _resolve_episode_sources(
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    for_list_seasons: bool,
    sources_override: list[str] | None,
    source_groups_override: list[GroupSource] | None,
) -> tuple[str, str, list[str], dict[str, GroupSource] | None]:
    slug, program_url = detect_slug(input_value)
    if sources_override is None:
        sources = discover_feed_sources(
            slug,
            selected_seasons,
            request_all_seasons,
            for_list_seasons,
        )
    else:
        sources = sources_override
    source_groups = (
        {group.url: group for group in source_groups_override}
        if source_groups_override is not None
        else None
    )
    return slug, program_url, sources, source_groups


def _collect_episode_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    for_list_seasons: bool,
    sources_override: list[str] | None = None,
    source_groups_override: list[GroupSource] | None = None,
) -> tuple[str, str, list[str], list[Episode], Path]:
    slug, program_url, sources, source_groups = _resolve_episode_sources(
        input_value,
        selected_seasons,
        request_all_seasons,
        for_list_seasons=for_list_seasons,
        sources_override=sources_override,
        source_groups_override=source_groups_override,
    )
    metadata_cache_file = settings.target_base / slug / ".metadata-cache.tsv"
    episodes = collect_episodes_from_sources(sources, source_groups=source_groups)
    return slug, program_url, sources, episodes, metadata_cache_file


def make_argument_parser(**kwargs: Any) -> argparse.ArgumentParser:
    kwargs.setdefault("formatter_class", argparse.RawTextHelpFormatter)
    return argparse.ArgumentParser(**kwargs)


def format_main_help() -> str:
    return "\n".join(
        [
            "usage: raiplaysound-cli [--version] <command>",
            "",
            "Python CLI for RaiPlaySound discovery and downloads.",
            "",
            "Commands:",
            "  list      Inspect stations, programs, seasons, or episodes",
            "  download  Download one program into the local music library",
            "",
            "Run `raiplaysound-cli <command> --help` for command-specific help.",
        ]
    )


def print_programs_text(programs: list[Any], mode: str) -> None:
    if mode == "sorted":
        ordered = sorted(programs, key=lambda item: (item.title.casefold(), item.slug))
        heading = f"Programs sorted alphabetically ({len(programs)}):"
    elif mode == "alpha":
        ordered = sorted(programs, key=lambda item: (item.title.casefold(), item.slug))
        heading = f"Programs grouped alphabetically ({len(programs)}):"
    else:
        ordered = sorted(
            programs,
            key=lambda item: (item.station_name.casefold(), item.title.casefold(), item.slug),
        )
        heading = f"Programs grouped by station ({len(programs)}):"
    table = Table(show_header=True)
    table.add_column("Name", overflow="fold")
    table.add_column("Slug", no_wrap=True)
    table.add_column("Station", no_wrap=True)
    table.add_column("Years", no_wrap=True)
    table.add_column("Groupings", justify="right", no_wrap=True)
    table.add_column("Description", overflow="fold", max_width=40)
    table.add_column("Page", overflow="fold", max_width=44)
    for program in ordered:
        table.add_row(
            str(program.title),
            str(program.slug),
            str(program.station_short),
            str(program.years),
            str(program.grouping_count) if getattr(program, "grouping_count", 0) > 0 else "—",
            str(program.description_excerpt or "—"),
            str(program.page_url),
        )
    console.print(heading)
    console.print(table)


def print_program_navigation_suggestions(programs: list[Any]) -> None:
    console.print("")
    console.print("Next:")
    console.print(
        "  one station:   raiplaysound-cli list programs --filter STATION_SLUG",
        soft_wrap=True,
    )
    console.print("  one program:   raiplaysound-cli list episodes PROGRAM_SLUG", soft_wrap=True)
    console.print("  download one:  raiplaysound-cli download PROGRAM_SLUG", soft_wrap=True)


def _load_station_program_counts(settings: Settings) -> dict[str, int]:
    if not program_cache_format_is_current(settings.catalog_cache_file):
        return {}
    counts: dict[str, int] = {}
    for program in load_cached_programs(settings.catalog_cache_file):
        counts[program.station_short] = counts.get(program.station_short, 0) + 1
    return counts


def print_station_table(
    stations: list[Any],
    *,
    counts: dict[str, int],
    detailed: bool,
) -> None:
    table = Table(show_header=True)
    table.add_column("Name", overflow="fold")
    table.add_column("Programs", justify="right", no_wrap=True)
    table.add_column("Slug", no_wrap=True)
    table.add_column("Page", overflow="fold", max_width=44)
    if detailed:
        table.add_column("Feed", overflow="fold", max_width=44)
    for station in stations:
        row = [
            str(station.name),
            str(counts.get(station.short, "?")),
            str(station.short),
            str(station.page_url),
        ]
        if detailed:
            row.append(str(station.feed_url))
        table.add_row(*row)
    console.print(table)


def print_station_program_suggestions(stations: list[Any]) -> None:
    console.print("")
    console.print("Next:")
    console.print(
        "  programs for one station: raiplaysound-cli list programs --filter STATION_SLUG",
        soft_wrap=True,
    )


def print_season_download_suggestions(slug: str, season_keys: list[str]) -> None:
    console.print("")
    console.print("Download:")
    console.print(f"  all episodes:  raiplaysound-cli download {slug}", soft_wrap=True)
    console.print(
        f"  all seasons:   raiplaysound-cli download {slug} --season all",
        soft_wrap=True,
    )
    if season_keys:
        console.print(
            f"  one season:    raiplaysound-cli download {slug} --season {season_keys[0]}",
            soft_wrap=True,
        )
    if len(season_keys) >= 2:
        console.print(
            f"  some seasons:  raiplaysound-cli download {slug} --season "
            f"{','.join(season_keys[:2])}",
            soft_wrap=True,
        )


def print_group_download_suggestions(slug: str, groups: list[Any]) -> None:
    console.print("")
    console.print("Download:")
    console.print(f"  all program episodes: raiplaysound-cli download {slug}", soft_wrap=True)
    if groups:
        console.print(
            f"  one grouping:         raiplaysound-cli download {slug} --group <selector>",
            soft_wrap=True,
        )
    if len(groups) >= 2:
        console.print(
            "  some groupings:       "
            f"raiplaysound-cli download {slug} --group "
            "<selector1>,<selector2>",
            soft_wrap=True,
        )


def print_episode_download_suggestions(
    slug: str,
    filtered: list[Episode],
    selected_seasons: set[str],
    request_all: bool,
    has_seasons: bool,
) -> None:
    console.print("")
    console.print("Download:")
    if has_seasons:
        if request_all:
            console.print(
                f"  all seasons:   raiplaysound-cli download {slug} --season all",
                soft_wrap=True,
            )
        elif selected_seasons:
            ordered = sorted(selected_seasons, key=season_sort_key)
            console.print(
                f"  listed season(s): raiplaysound-cli download {slug} --season "
                f"{','.join(ordered)}",
                soft_wrap=True,
            )
        else:
            console.print(
                f"  current/default season: raiplaysound-cli download {slug}",
                soft_wrap=True,
            )
        console.print(
            f"  all program episodes:   raiplaysound-cli download {slug} --season all",
            soft_wrap=True,
        )
    else:
        console.print(
            f"  all program episodes:   raiplaysound-cli download {slug}",
            soft_wrap=True,
        )
    if filtered:
        console.print(
            f"  one episode:    raiplaysound-cli download {slug} --episode-ids "
            f"{filtered[0].episode_id}",
            soft_wrap=True,
        )
    if len(filtered) >= 2:
        console.print(
            f"  some episodes:  raiplaysound-cli download {slug} --episode-ids "
            f"{filtered[0].episode_id},{filtered[1].episode_id}",
            soft_wrap=True,
        )


def print_download_prep_step(message: str) -> None:
    console.print(f"[dim]Preparing:[/dim] {message}")


def list_output_context(use_pager: bool):
    return console.pager(styles=True) if use_pager else nullcontext()


def _display_group_kind(kind: str) -> str:
    return kind.replace("_", " ").title()


def _dedupe_listing_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        marker = (str(item.get("kind", "")).lower(), str(item.get("key", "")).lower())
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def print_grouping_table(slug: str, items: list[dict[str, Any]], *, all_seasons: bool) -> None:
    table = Table(show_header=True)
    table.add_column("Program", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Name", overflow="fold")
    table.add_column("Episodes", justify="right")
    table.add_column("Selector", overflow="fold")
    table.add_column("Published", no_wrap=True)
    for item in items:
        kind = "Season" if all_seasons else _display_group_kind(str(item["kind"]))
        name = f"Season {item['key']}" if all_seasons else str(item["label"])
        table.add_row(
            slug,
            kind,
            name,
            str(item["episodes"]),
            str(item["key"]),
            str(item["published"]),
        )
    console.print(table)


def load_show_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    for_list_seasons: bool = False,
    sources_override: list[str] | None = None,
    source_groups_override: list[GroupSource] | None = None,
) -> tuple[str, str, list[Any], Any, Path]:
    slug, program_url, sources, episodes, metadata_cache_file = _collect_episode_context(
        settings,
        input_value,
        selected_seasons,
        request_all_seasons,
        for_list_seasons=for_list_seasons,
        sources_override=sources_override,
        source_groups_override=source_groups_override,
    )
    cache: dict[str, tuple[str, str, str]] = {}
    if not settings.force_refresh_metadata and cache_file_is_fresh(
        metadata_cache_file, settings.metadata_max_age_hours
    ):
        cache = load_metadata_cache(metadata_cache_file)
    need_refresh = any(
        not cache_entry_is_complete(cache.get(episode.episode_id)) for episode in episodes
    )
    if settings.force_refresh_metadata or need_refresh:
        cache.update(collect_metadata(sources))
        write_metadata_cache(metadata_cache_file, cache)
    summary = normalize_episode_metadata(episodes, cache)
    return slug, program_url, episodes, summary, metadata_cache_file


def load_list_episode_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    sources_override: list[str] | None = None,
    source_groups_override: list[GroupSource] | None = None,
) -> tuple[str, str, list[Any], Any]:
    slug, program_url, _sources, episodes, metadata_cache_file = _collect_episode_context(
        settings,
        input_value,
        selected_seasons,
        request_all_seasons,
        for_list_seasons=False,
        sources_override=sources_override,
        source_groups_override=source_groups_override,
    )
    cache = load_metadata_cache(metadata_cache_file)
    summary = normalize_episode_metadata(episodes, cache)
    return slug, program_url, episodes, summary


def load_cached_show_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    sources_override: list[str] | None = None,
    source_groups_override: list[GroupSource] | None = None,
) -> tuple[str, str, list[Any], Any, Path, dict[str, tuple[str, str, str]]]:
    slug, program_url, _sources, episodes, metadata_cache_file = _collect_episode_context(
        settings,
        input_value,
        selected_seasons,
        request_all_seasons,
        for_list_seasons=False,
        sources_override=sources_override,
        source_groups_override=source_groups_override,
    )
    cache: dict[str, tuple[str, str, str]] = {}
    if not settings.force_refresh_metadata and cache_file_is_fresh(
        metadata_cache_file, settings.metadata_max_age_hours
    ):
        cache = load_metadata_cache(metadata_cache_file)
    summary = normalize_episode_metadata(episodes, cache)
    return slug, program_url, episodes, summary, metadata_cache_file, cache


def list_stations(_settings: Settings, args: argparse.Namespace) -> int:
    try:
        stations = parse_stations(http_get("https://www.raiplaysound.it/dirette.json"))
    except ValueError as exc:
        raise CLIError("invalid RaiPlaySound station payload.") from exc
    counts = _load_station_program_counts(_settings)
    if args.json:
        json_dump(
            {
                "mode": "stations",
                "count": len(stations),
                "detailed": args.detailed,
                "program_counts_available": bool(counts),
                "stations": [dataclasses.asdict(item) for item in stations],
            }
        )
        return 0
    with list_output_context(args.pager):
        console.print(f"Available RaiPlaySound radio stations ({len(stations)}):")
        print_station_table(stations, counts=counts, detailed=args.detailed)
        print_station_program_suggestions(stations)
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
    if args.sorted:
        mode = "sorted"
    elif args.group_by == "alpha" or (args.group_by == "auto" and station_filter):
        mode = "alpha"
    else:
        mode = "station"
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
    with list_output_context(args.pager):
        print_programs_text(programs, mode)
        print_program_navigation_suggestions(programs)
    return 0


def list_seasons(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    slug, program_url = detect_slug(args.input)
    payload = load_season_listing_payload(settings, slug)
    program_url = str(payload["program_url"])
    items = _dedupe_listing_items([dict(item) for item in payload["items"]])
    has_groups = bool(payload["has_groups"])
    all_seasons = bool(payload["has_seasons"]) and all(
        str(item["kind"]) == "season" for item in items
    )
    if has_groups:
        if not all_seasons and (selected_seasons or request_all):
            raise CLIError("this program does not expose seasons, so --season cannot be used.")
        if all_seasons and selected_seasons and not request_all:
            available = {str(item["key"]) for item in items}
            missing = sorted(selected_seasons - available, key=season_sort_key)
            if missing:
                raise CLIError(f"season {missing[0]} is not available.")
            items = [item for item in items if str(item["key"]) in selected_seasons]
    if args.json:
        has_seasons = bool(payload["has_seasons"])
        if not has_groups and not has_seasons and (selected_seasons or request_all):
            raise CLIError("this program does not expose seasons, so --season cannot be used.")
        if not has_groups and has_seasons and selected_seasons and not request_all:
            available = {str(item["key"]) for item in items}
            missing = sorted(selected_seasons - available, key=season_sort_key)
            if missing:
                raise CLIError(f"season {missing[0]} is not available.")
            items = [item for item in items if str(item["key"]) in selected_seasons]
        json_dump(
            {
                "mode": "seasons",
                "slug": slug,
                "program_url": program_url,
                "has_seasons": has_seasons,
                "has_groups": has_groups,
                "items": items,
            }
        )
        return 0
    with list_output_context(args.pager):
        if has_groups:
            if all_seasons:
                console.print(f"Available seasons for {slug} ({program_url}):")
                sorted_items = sorted(items, key=lambda item: season_sort_key(str(item["key"])))
                print_grouping_table(slug, sorted_items, all_seasons=True)
                print_season_download_suggestions(slug, [str(item["key"]) for item in sorted_items])
                return 0
            console.print(f"Available groupings for {slug} ({program_url}):")
            print_grouping_table(slug, items, all_seasons=False)
            print_group_download_suggestions(
                slug,
                [
                    type(
                        "GroupSummaryProxy",
                        (),
                        {
                            "key": item["key"],
                            "label": item["label"],
                            "url": item["url"],
                            "kind": item["kind"],
                        },
                    )()
                    for item in items
                ],
            )
            return 0
        has_seasons = bool(payload["has_seasons"])
        if not has_seasons:
            if selected_seasons or request_all:
                raise CLIError("this program does not expose seasons, so --season cannot be used.")
            console.print(f"No seasons detected for {slug} ({program_url}).")
            console.print(
                f"  - Episodes: {items[0]['episodes']} " f"(published: {items[0]['published']})"
            )
            return 0
        console.print(f"Available seasons for {slug} ({program_url}):")
        available = {str(item["key"]) for item in items}
        if selected_seasons and not request_all:
            missing = sorted(selected_seasons - available, key=season_sort_key)
            if missing:
                raise CLIError(f"season {missing[0]} is not available.")
        sorted_items = [
            item
            for item in sorted(items, key=lambda entry: season_sort_key(str(entry["key"])))
            if not selected_seasons or request_all or str(item["key"]) in selected_seasons
        ]
        print_grouping_table(slug, sorted_items, all_seasons=True)
        print_season_download_suggestions(slug, [str(item["key"]) for item in sorted_items])
    return 0


def list_episodes(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    selected_groups = build_requested_groups(args.group or settings.groups_arg)
    input_value = args.input
    slug, program_url = detect_slug(input_value)
    sources_override, groups, non_season_groups = discover_grouped_episode_sources(
        slug,
        selected_seasons,
        request_all,
        selected_groups,
    )
    slug, program_url, cache_sources = _episode_listing_cache_sources(
        input_value,
        selected_seasons,
        request_all,
        sources_override=sources_override,
        source_groups_override=groups,
    )
    cache_file = _episode_list_cache_file(settings, slug, cache_sources)
    if cache_file_is_fresh(cache_file, LIST_CACHE_MAX_AGE_HOURS):
        try:
            payload = _load_json_cache(cache_file)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            payload = {}
        if payload.get("version") == LIST_CACHE_VERSION:
            slug, program_url, episodes, summary = _context_from_episode_payload(payload)
        else:
            slug, program_url, episodes, summary = load_list_episode_context(
                settings,
                input_value,
                selected_seasons,
                request_all,
                sources_override=sources_override,
                source_groups_override=groups,
            )
            _write_json_cache(
                cache_file, _episode_payload_from_context(slug, program_url, summary, episodes)
            )
    else:
        slug, program_url, episodes, summary = load_list_episode_context(
            settings,
            input_value,
            selected_seasons,
            request_all,
            sources_override=sources_override,
            source_groups_override=groups,
        )
        _write_json_cache(
            cache_file,
            _episode_payload_from_context(slug, program_url, summary, episodes),
        )
    if non_season_groups:
        summary.has_seasons = False
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
                        "group": episode.group_label,
                        "group_kind": episode.group_kind,
                        "season": episode.season if summary.has_seasons else None,
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
    elif non_season_groups:
        table.add_column("Group")
    table.add_column("Date")
    table.add_column("Episode")
    table.add_column("ID")
    if args.show_urls:
        table.add_column("URL")
    for episode in filtered:
        row = []
        if summary.has_seasons:
            row.append(f"S{episode.season}")
        elif non_season_groups:
            row.append(episode.group_label or episode.group_kind or "default")
        row.extend([episode.pretty_date, episode.title, episode.episode_id])
        if args.show_urls:
            row.append(episode.url)
        table.add_row(*row)
    with list_output_context(args.pager):
        console.print(f"Episodes for {slug} ({program_url}):")
        console.print(table)
        print_episode_download_suggestions(
            slug,
            filtered,
            selected_seasons,
            request_all,
            summary.has_seasons,
        )
    return 0


def build_list_parser() -> argparse.ArgumentParser:
    parser = make_argument_parser(
        prog="raiplaysound-cli list",
        usage=(
            "raiplaysound-cli list <stations|programs|seasons|episodes> "
            "[PROGRAM_SLUG_OR_URL] [options]"
        ),
        description="Inspect RaiPlaySound stations, programs, seasons, or episodes.",
        epilog=(
            "Examples:\n"
            "  raiplaysound-cli list stations\n"
            "  raiplaysound-cli list programs --filter STATION_SLUG\n"
            "  raiplaysound-cli list seasons PROGRAM_SLUG\n"
            "  raiplaysound-cli list episodes PROGRAM_SLUG --group GROUP_SLUG\n"
            "  raiplaysound-cli list episodes PROGRAM_SLUG --season SEASON_NUMBER --show-urls"
        ),
        add_help=False,
        color=False,
    )
    parser.add_argument(
        "positional_a",
        nargs="?",
        metavar="TARGET",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "positional_b",
        nargs="?",
        metavar="PROGRAM_SLUG_OR_URL",
        help=(
            "For `seasons` and `episodes`: a program slug or full URL. Examples: "
            "`PROGRAM_SLUG`, `https://www.raiplaysound.it/programmi/PROGRAM_SLUG`."
        ),
    )
    general_group = parser.add_argument_group("General")
    general_group.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of a table.",
    )
    output_group.add_argument(
        "--show-urls",
        action="store_true",
        help="Include source URLs in `list episodes` output.",
    )
    output_group.add_argument(
        "--pager",
        action="store_true",
        help="Show text output through a pager.",
    )
    station_group = parser.add_argument_group("Stations")
    station_group.add_argument(
        "--detailed",
        action="store_true",
        help="Include page and feed URLs with `list stations`.",
    )
    program_group = parser.add_argument_group("Programs")
    program_group.add_argument(
        "--group-by",
        choices=["auto", "alpha", "station"],
        default="auto",
        help="How to group `list programs` results.",
    )
    program_group.add_argument(
        "--filter",
        default="",
        help="Only show programs for one station slug (`STATION_SLUG`).",
    )
    program_group.add_argument(
        "--sorted",
        action="store_true",
        help="Show one flat alphabetical list.",
    )
    program_group.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Only for `list programs`. Refresh the cached program catalog.",
    )
    program_group.add_argument(
        "--catalog-max-age-hours",
        type=int,
        default=2160,
        help="Only for `list programs`. Refresh the catalog after this many hours.",
    )
    episode_group = parser.add_argument_group("Episodes")
    episode_group.add_argument(
        "--season",
        default="",
        help="For seasonal programs. Accepts `SEASON_NUMBER` or a comma-separated list.",
    )
    episode_group.add_argument(
        "--group",
        default="",
        help="For `list episodes`. Use grouping slugs shown by `list seasons`.",
    )
    return parser


def build_download_parser() -> argparse.ArgumentParser:
    parser = make_argument_parser(
        prog="raiplaysound-cli download",
        usage="raiplaysound-cli download PROGRAM_SLUG_OR_URL [options]",
        description=(
            "Download RaiPlaySound episodes into TARGET_BASE/<slug>/.\n\n"
            "Repeat runs stay safe through `.download-archive.txt`."
        ),
        epilog=(
            "Examples:\n"
            "  raiplaysound-cli download PROGRAM_SLUG\n"
            "  raiplaysound-cli download PROGRAM_SLUG --season SEASON_NUMBER\n"
            "  raiplaysound-cli download PROGRAM_SLUG --group GROUP_SLUG\n"
            "  raiplaysound-cli download PROGRAM_SLUG --episode-ids "
            "EPISODE_ID_1,EPISODE_ID_2\n"
            "  raiplaysound-cli download PROGRAM_SLUG --rss --playlist"
        ),
        add_help=False,
        color=False,
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="PROGRAM_SLUG_OR_URL",
        help="Program slug or full program URL.",
    )
    general_group = parser.add_argument_group("General")
    general_group.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    selection_group = parser.add_argument_group("Selection")
    selection_group.add_argument(
        "-f",
        "--format",
        default=None,
        help="Target audio format.",
    )
    selection_group.add_argument(
        "-s",
        "--season",
        default="",
        help="For seasonal programs. Accepts `SEASON_NUMBER` or a comma-separated list.",
    )
    selection_group.add_argument(
        "--group",
        default="",
        help="For grouped programs. Use grouping slugs shown by `list seasons`.",
    )
    selection_group.add_argument(
        "--seasons",
        dest="season_alias",
        default="",
        help=argparse.SUPPRESS,
    )
    selection_group.add_argument(
        "--episode-ids",
        default="",
        help="Comma-separated episode IDs to download.",
    )
    selection_group.add_argument(
        "--episodes",
        dest="episodes_legacy",
        default="",
        help=argparse.SUPPRESS,
    )
    selection_group.add_argument(
        "--episode-url",
        action="append",
        default=[],
        help="Download a specific episode URL.",
    )
    selection_group.add_argument(
        "--episode-urls",
        default="",
        help="Comma-separated episode URLs to download.",
    )
    execution_group = parser.add_argument_group("Execution")
    execution_group.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of concurrent download jobs.",
    )
    execution_group.add_argument(
        "-m",
        "--missing",
        action="store_true",
        help="Re-download archive-marked files missing locally.",
    )
    execution_group.add_argument(
        "--log",
        nargs="?",
        const="__enable__",
        default=None,
        help="Enable run logging, optionally to a file path.",
    )
    execution_group.add_argument(
        "--debug-pids",
        action="store_true",
        help="Log worker and `yt-dlp` PID transitions.",
    )
    metadata_group = parser.add_argument_group("Metadata and Cache")
    metadata_group.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="Refresh the per-show metadata cache.",
    )
    metadata_group.add_argument(
        "--clear-metadata-cache",
        action="store_true",
        help="Delete the per-show metadata cache before refresh.",
    )
    metadata_group.add_argument(
        "--metadata-max-age-hours",
        type=int,
        default=None,
        help="Maximum metadata cache age in hours.",
    )
    output_group = parser.add_argument_group("Outputs")
    output_group.add_argument(
        "--rss",
        dest="rss",
        action="store_true",
        help="Generate `feed.xml` after the download run.",
    )
    output_group.add_argument(
        "--no-rss",
        dest="rss",
        action="store_false",
        help="Disable RSS generation.",
    )
    parser.set_defaults(rss=None)
    output_group.add_argument(
        "--rss-base-url",
        default=None,
        help="Public base URL used for RSS enclosure links.",
    )
    output_group.add_argument(
        "--playlist",
        dest="playlist",
        action="store_true",
        help="Generate `playlist.m3u` after the download run.",
    )
    output_group.add_argument(
        "--no-playlist",
        dest="playlist",
        action="store_false",
        help="Disable playlist generation.",
    )
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
    if settings.show_urls and not args.show_urls:
        args.show_urls = True
    if settings.pager and not args.pager:
        args.pager = True
    if settings.stations_detailed and not args.detailed:
        args.detailed = True
    if not args.filter and settings.station_filter:
        args.filter = settings.station_filter
    if args.group_by == "auto" and settings.group_by != "auto":
        args.group_by = settings.group_by
    if not args.sorted and settings.podcasts_sorted:
        args.sorted = True
    return args


def predicted_media_exists(episode_url: str, output_template: str, audio_format: str) -> bool:
    parse_metadata_expr = (
        r"title:^(?P<series>.+?) "
        r"S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$"
    )
    try:
        result = run_yt_dlp(
            [
                "--skip-download",
                "--parse-metadata",
                parse_metadata_expr,
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
    for ext in [
        audio_format,
        "mp3",
        "m4a",
        "aac",
        "ogg",
        "opus",
        "flac",
        "wav",
        "mp4",
        "webm",
        "m4b",
    ]:
        if Path(f"{base}.{ext}").exists():
            return True
    return False


def download_command(settings: Settings, args: argparse.Namespace) -> int:
    slug, program_url = detect_slug(args.input or settings.input_value)
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    selected_groups = build_requested_groups(args.group or settings.groups_arg)
    requested_episode_ids, requested_episode_urls = build_requested_episode_filters(
        args.episode_ids or settings.episodes_arg,
        ",".join(args.episode_url or [])
        + ("," if args.episode_url and (args.episode_urls or settings.episode_urls_arg) else "")
        + (args.episode_urls or settings.episode_urls_arg),
    )
    target_dir = settings.target_base / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_file = target_dir / ".download-archive.txt"
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    if settings.clear_metadata_cache and metadata_cache_file.exists():
        metadata_cache_file.unlink()
    print_download_prep_step("discovering groupings and sources")
    sources_override, groups, non_season_groups = discover_grouped_episode_sources(
        slug,
        selected_seasons,
        request_all,
        selected_groups,
    )
    print_download_prep_step("enumerating episodes and loading cached metadata")
    slug, program_url, episodes, summary, metadata_cache_file, cache = load_cached_show_context(
        settings,
        args.input or settings.input_value,
        selected_seasons,
        request_all,
        sources_override=sources_override,
        source_groups_override=groups,
    )
    if non_season_groups:
        summary.has_seasons = False
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
    print_download_prep_step(f"selected {len(filtered)} episode(s) for download")
    need_refresh = settings.force_refresh_metadata or any(
        not cache_entry_is_complete(cache.get(episode.episode_id)) for episode in filtered
    )
    if need_refresh:
        print_download_prep_step("refreshing metadata for selected episodes")
        cache.update(collect_metadata([episode.url for episode in filtered], single_entries=True))
        write_metadata_cache(metadata_cache_file, cache)
    filtered_summary = normalize_episode_metadata(filtered, cache)
    if non_season_groups:
        filtered_summary.has_seasons = False
    if filtered_summary.has_seasons:
        season_template = (
            "%(series,playlist_title,uploader)s - "
            "S%(season_number|0)02d%(episode_number|0)02d - "
            "%(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s"
        )
        output_template = str(target_dir / season_template)
    else:
        episode_template = (
            "%(series,playlist_title,uploader)s - "
            "%(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s"
        )
        output_template = str(target_dir / episode_template)
    archived_ids: set[str] = set()
    if archive_file.exists():
        archive_lines = archive_file.read_text(encoding="utf-8").splitlines()
        archived_ids = {
            parts[1]
            for parts in (line.split(maxsplit=2) for line in archive_lines)
            if len(parts) >= 2
        }
    missing_archived_ids: set[str] = set()
    if archived_ids and settings.auto_redownload_missing:
        print_download_prep_step("checking archived entries for missing local files")
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.check_jobs) as executor:
            check_futures: dict[
                concurrent.futures.Future[bool],
                Episode,
            ] = {
                executor.submit(
                    predicted_media_exists,
                    episode.url,
                    output_template,
                    settings.audio_format,
                ): episode
                for episode in filtered
                if episode.episode_id in archived_ids
            }
            for check_future in concurrent.futures.as_completed(check_futures):
                if not check_future.result():
                    missing_archived_ids.add(check_futures[check_future].episode_id)
        if missing_archived_ids:
            remove_missing_ids_from_archive(archive_file, missing_archived_ids)
    log_file = resolve_log_file(
        enable_log=settings.enable_log,
        debug_pids=settings.debug_pids,
        log_path_arg=settings.log_path_arg,
        target_dir=target_dir,
        slug=slug,
    )
    lock_dir = target_dir / ".run-lock"
    acquire_lock(lock_dir, slug)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("{task.fields[size_text]}"),
        TextColumn("{task.fields[speed_text]}"),
        TimeRemainingColumn(),
        console=console,
    )
    downloader: Downloader | None = None
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    work_root = target_dir / ".run-work"
    try:
        console.print(f"Starting downloads for {slug} ({len(filtered)} episode(s))")
        with progress:
            overall_label = f"[bold]Total ({len(filtered)} episode(s))[/bold]"
            overall = progress.add_task(
                overall_label,
                total=len(filtered),
                size_text="",
                speed_text="",
            )
            downloader = Downloader(
                archive_file=archive_file,
                output_template=output_template,
                work_root=work_root,
                audio_format=settings.audio_format,
                log_file=log_file,
                rich_progress=progress,
                debug_pids=settings.debug_pids,
                overall_task_id=overall,
            )

            def _handle_signal(signum: int, _frame: Any) -> None:
                if downloader is not None:
                    downloader.terminate_all()
                raise KeyboardInterrupt(f"signal {signum}")

            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
            tasks = [
                DownloadTask(
                    episode_id=episode.episode_id,
                    episode_url=episode.url,
                    episode_label=episode.label,
                    task_id=progress.add_task(
                        f"download {episode.label}",
                        total=100,
                        size_text="0.0 MB",
                        speed_text="",
                    ),
                )
                for episode in filtered
            ]
            done_count = skip_count = error_count = 0
            conversion_workers = max(1, min(settings.jobs, 2))
            with (
                concurrent.futures.ThreadPoolExecutor(
                    max_workers=settings.jobs
                ) as download_executor,
                concurrent.futures.ThreadPoolExecutor(
                    max_workers=conversion_workers
                ) as convert_executor,
            ):
                pending_downloads: dict[concurrent.futures.Future[Any], DownloadTask] = {}
                pending_conversions: dict[concurrent.futures.Future[Any], DownloadTask] = {}
                for task in tasks:
                    if (
                        task.episode_id in archived_ids
                        and task.episode_id not in missing_archived_ids
                    ):
                        progress.update(
                            task.task_id,
                            description=f"skip {task.episode_label}",
                            completed=100,
                            total=100,
                            size_text="",
                            speed_text="",
                        )
                        progress.remove_task(task.task_id)
                        progress.advance(overall, 1)
                        skip_count += 1
                        continue
                    future = download_executor.submit(downloader.download_source, task)
                    pending_downloads[future] = task
                while pending_downloads or pending_conversions:
                    completed, _pending = concurrent.futures.wait(
                        [*pending_downloads, *pending_conversions],
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for future in completed:
                        if future in pending_downloads:
                            task = pending_downloads.pop(future)
                            state, _detail, prepared = future.result()
                            if state == "READY" and prepared is not None:
                                convert_future = convert_executor.submit(
                                    downloader.convert_one, task, prepared
                                )
                                pending_conversions[convert_future] = task
                                continue
                            progress.advance(overall, 1)
                            error_count += 1
                            continue
                        task = pending_conversions.pop(future)
                        conversion_future = cast(concurrent.futures.Future[tuple[str, str]], future)
                        state, _detail = conversion_future.result()
                        progress.advance(overall, 1)
                        if state == "DONE":
                            done_count += 1
                        elif state == "SKIP":
                            skip_count += 1
                        else:
                            error_count += 1
            console.print(
                f"Completed: done={done_count}, skipped={skip_count}, errors={error_count}"
            )
            if error_count:
                return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        release_lock(lock_dir)
        shutil.rmtree(work_root, ignore_errors=True)
    if settings.rss_feed:
        generate_rss_feed(target_dir, slug, program_url, metadata_cache_file, settings.rss_base_url)
    if settings.playlist:
        generate_playlist(target_dir, metadata_cache_file)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        console.print(format_main_help())
        return 0
    if len(argv) == 1 and argv[0] == "--version":
        console.print(f"raiplaysound-cli {__version__}")
        return 0
    if len(argv) == 1 and argv[0] in {"-h", "--help"}:
        console.print(format_main_help())
        return 0
    config = parse_env_file(Path.home() / ".raiplaysound-cli.conf")
    if not config:
        legacy = Path.home() / ".raiplaysound-downloader.conf"
        if legacy.exists():
            config = parse_env_file(legacy)
    try:
        settings = Settings.from_config(config)
        command, rest = choose_command(argv, config)
        if command == "list":
            args = apply_list_defaults(settings, build_list_parser().parse_args(rest))
            target = ""
            input_value = args.positional_a
            if args.positional_a in {"stations", "programs", "seasons", "episodes"}:
                target = args.positional_a
                input_value = args.positional_b
            elif settings.list_target in {"stations", "programs", "seasons", "episodes"}:
                target = settings.list_target
            args.input = input_value or settings.input_value
            if target not in {"stations", "programs", "seasons", "episodes"}:
                raise CLIError(
                    "list mode requires exactly one positional target: "
                    "stations, programs, seasons, or episodes."
                )
            if target == "stations":
                if args.group:
                    raise CLIError("--group can only be used with list episodes.")
                return list_stations(settings, args)
            if target == "programs":
                if args.group:
                    raise CLIError("--group can only be used with list episodes.")
                return list_programs(settings, args)
            if target == "seasons":
                if args.group:
                    raise CLIError("--group can only be used with list episodes.")
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
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 1
