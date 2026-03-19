from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import signal
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
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
    write_metadata_cache,
    year_span,
)
from .errors import CLIError
from .models import Episode, GroupSource
from .outputs import generate_playlist, generate_rss_feed
from .runtime import acquire_lock, http_get, release_lock, run_yt_dlp

console = Console()
err_console = Console(stderr=True)


def json_dump(data: Any) -> None:
    console.print(json.dumps(data, indent=2, ensure_ascii=False))


def make_argument_parser(**kwargs: Any) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(**kwargs)


def format_main_help() -> str:
    return "\n\n".join(
        [
            "\n".join(
                [
                    "usage: raiplaysound-cli [--version] <command> [options]",
                    "",
                    "Python CLI for RaiPlaySound discovery and downloads.",
                    "",
                    "Commands:",
                    "  list      Inspect stations, programs, seasons, or episodes",
                    "  download  Download one program into the local music library",
                    "",
                    "Preferred list forms:",
                    "  raiplaysound-cli list stations",
                    "  raiplaysound-cli list programs",
                    "  raiplaysound-cli list seasons <program_slug|program_url>",
                    "  raiplaysound-cli list episodes <program_slug|program_url>",
                    "",
                    "Run `raiplaysound-cli <command> --help` for command-specific help.",
                ]
            ),
            build_list_parser().format_help().rstrip(),
            build_download_parser().format_help().rstrip(),
        ]
    )


def print_programs_text(programs: list[Any], mode: str) -> None:
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
            console.print(
                f"  - {program.title} ({program.slug}) "
                f"[{program.station_name}:{program.station_short} | {program.years}]"
            )
        return
    console.print(f"Programs grouped by station ({len(programs)}):")
    current_station = None
    for program in sorted(
        programs,
        key=lambda item: (item.station_name.casefold(), item.title.casefold(), item.slug),
    ):
        station_key = (program.station_name, program.station_short)
        if station_key != current_station:
            current_station = station_key
            console.print("")
            console.print(f"[{program.station_name} | {program.station_short}]")
        console.print(f"  - {program.title} ({program.slug}) [{program.years}]")


def print_program_download_suggestion() -> None:
    console.print("")
    console.print("Download:")
    console.print("  raiplaysound-cli download <program_slug>", soft_wrap=True)


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
            ordered = sorted(selected_seasons, key=int)
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
    slug, program_url = detect_slug(input_value)
    target_dir = settings.target_base / slug
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
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
    episodes = collect_episodes_from_sources(sources, source_groups=source_groups)
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


def list_stations(_settings: Settings, args: argparse.Namespace) -> int:
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
    if args.detailed:
        console.print("Available RaiPlaySound radio stations (detailed):")
    else:
        console.print("Available RaiPlaySound radio stations (station slug -> name):")
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
    print_programs_text(programs, mode)
    print_program_download_suggestion()
    return 0


def list_seasons(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    slug, program_url = detect_slug(args.input)
    _, groups = discover_group_listing_sources(slug)
    if groups:
        group_summaries = collect_group_summaries(groups)
        all_seasons = all(group.kind == "season" for group in group_summaries)
        if not all_seasons and (selected_seasons or request_all):
            raise CLIError("this program does not expose seasons, so --season cannot be used.")
        if all_seasons and selected_seasons and not request_all:
            available = {group.key for group in group_summaries}
            missing = sorted(selected_seasons - available, key=int)
            if missing:
                raise CLIError(f"season {missing[0]} is not available.")
            group_summaries = [group for group in group_summaries if group.key in selected_seasons]
    else:
        group_summaries = []
        all_seasons = False
    if args.json:
        items = []
        has_seasons = all_seasons
        if group_summaries:
            for group in group_summaries:
                items.append(
                    {
                        "key": group.key,
                        "label": group.label,
                        "kind": group.kind,
                        "episodes": group.episodes,
                        "published": year_span(group.year_min, group.year_max),
                        "url": group.url,
                    }
                )
        else:
            _, sources = discover_season_listing_sources(slug)
            episodes, summary = collect_season_summary_from_sources(sources)
            has_seasons = summary.has_seasons
            if not summary.has_seasons:
                if selected_seasons or request_all:
                    raise CLIError(
                        "this program does not expose seasons, so --season cannot be used."
                    )
                items.append(
                    {
                        "key": "default",
                        "label": "All episodes",
                        "kind": "flat",
                        "episodes": len(episodes),
                        "published": year_span(summary.show_year_min, summary.show_year_max),
                        "url": program_url,
                    }
                )
            else:
                available = set(summary.counts)
                if selected_seasons and not request_all:
                    missing = sorted(selected_seasons - available, key=int)
                    if missing:
                        raise CLIError(f"season {missing[0]} is not available.")
                for season in sorted(summary.counts, key=lambda item: int(item)):
                    if selected_seasons and not request_all and season not in selected_seasons:
                        continue
                    items.append(
                        {
                            "key": season,
                            "label": f"Season {season}",
                            "kind": "season",
                            "episodes": summary.counts[season],
                            "published": year_span(
                                summary.year_min.get(season, ""),
                                summary.year_max.get(season, ""),
                            ),
                            "url": f"{program_url}/stagione-{season}",
                        }
                    )
        json_dump(
            {
                "mode": "seasons",
                "slug": slug,
                "program_url": program_url,
                "has_seasons": has_seasons,
                "has_groups": bool(group_summaries),
                "items": items,
            }
        )
        return 0
    if group_summaries:
        if all_seasons:
            console.print(f"Available seasons for {slug} ({program_url}):")
            sorted_groups = sorted(group_summaries, key=lambda item: int(item.key))
            for group in sorted_groups:
                published = year_span(group.year_min, group.year_max)
                console.print(
                    f"  - Season {group.key}: {group.episodes} episodes "
                    f"(published: {published})"
                )
            print_season_download_suggestions(slug, [group.key for group in sorted_groups])
            return 0
        console.print(f"Available groupings for {slug} ({program_url}):")
        for group in group_summaries:
            published = year_span(group.year_min, group.year_max)
            console.print(
                f"  - {group.label}: {group.episodes} episodes "
                f"({group.kind}; published: {published})"
            )
        console.print("")
        console.print("Download:")
        console.print(f"  all program episodes: raiplaysound-cli download {slug}")
        return 0
    _, sources = discover_season_listing_sources(slug)
    episodes, summary = collect_season_summary_from_sources(sources)
    if not summary.has_seasons:
        if selected_seasons or request_all:
            raise CLIError("this program does not expose seasons, so --season cannot be used.")
        console.print(f"No seasons detected for {slug} ({program_url}).")
        console.print(
            f"  - Episodes: {len(episodes)} "
            f"(published: {year_span(summary.show_year_min, summary.show_year_max)})"
        )
        return 0
    console.print(f"Available seasons for {slug} ({program_url}):")
    available = set(summary.counts)
    if selected_seasons and not request_all:
        missing = sorted(selected_seasons - available, key=int)
        if missing:
            raise CLIError(f"season {missing[0]} is not available.")
    sorted_seasons = [
        season
        for season in sorted(summary.counts, key=lambda item: int(item))
        if not selected_seasons or request_all or season in selected_seasons
    ]
    for season in sorted_seasons:
        published = year_span(
            summary.year_min.get(season, ""),
            summary.year_max.get(season, ""),
        )
        console.print(
            f"  - Season {season}: {summary.counts[season]} episodes " f"(published: {published})"
        )
    print_season_download_suggestions(slug, sorted_seasons)
    return 0


def list_episodes(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    input_value = args.input
    slug, _program_url = detect_slug(input_value)
    sources_override, groups, non_season_groups = discover_grouped_episode_sources(
        slug,
        selected_seasons,
        request_all,
    )
    slug, program_url, episodes, summary, _metadata_cache = load_show_context(
        settings,
        input_value,
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
        usage="raiplaysound-cli list <stations|programs|seasons|episodes> [INPUT] [options]",
        description="Inspect RaiPlaySound stations, programs, seasons, or episodes.",
        color=False,
    )
    parser.add_argument(
        "positional_a",
        nargs="?",
        metavar="TARGET_OR_INPUT",
        help=(
            "Preferred positional target (`stations`, `programs`, `seasons`, `episodes`) "
            "or program input."
        ),
    )
    parser.add_argument(
        "positional_b",
        nargs="?",
        metavar="INPUT",
        help="Optional program slug or program URL when the target is given positionally.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show extra station details with `list stations`.",
    )
    parser.add_argument(
        "--group-by",
        choices=["auto", "alpha", "station"],
        default="auto",
        help="Program grouping mode for `list programs`.",
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Filter programs by station slug.",
    )
    parser.add_argument(
        "--sorted",
        action="store_true",
        help="Sort program output alphabetically.",
    )
    parser.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Refresh the cached program catalog.",
    )
    parser.add_argument(
        "--catalog-max-age-hours",
        type=int,
        default=2160,
        help="Maximum catalog cache age in hours before refresh.",
    )
    parser.add_argument(
        "--show-urls",
        action="store_true",
        help="Show episode URLs in `list episodes` output.",
    )
    parser.add_argument(
        "--season",
        default="",
        help="Restrict listing to one or more seasons.",
    )
    return parser


def build_download_parser() -> argparse.ArgumentParser:
    parser = make_argument_parser(
        prog="raiplaysound-cli download",
        usage="raiplaysound-cli download [options] <program_slug|program_url>",
        description="Download RaiPlaySound episodes into the local music library.",
        color=False,
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="INPUT",
        help="Program slug or full program URL.",
    )
    parser.add_argument(
        "-f",
        "--format",
        default=None,
        help="Target audio format.",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of concurrent download jobs.",
    )
    parser.add_argument(
        "-s",
        "--season",
        default="",
        help="Restrict downloads to one or more seasons.",
    )
    parser.add_argument(
        "--seasons",
        dest="season_alias",
        default="",
        help="Legacy alias for `--season`.",
    )
    parser.add_argument(
        "--episode-ids",
        default="",
        help="Comma-separated episode IDs to download.",
    )
    parser.add_argument(
        "--episodes",
        dest="episodes_legacy",
        default="",
        help="Legacy alias for `--episode-ids`.",
    )
    parser.add_argument(
        "--episode-url",
        action="append",
        default=[],
        help="Download a specific episode URL.",
    )
    parser.add_argument(
        "--episode-urls",
        default="",
        help="Comma-separated episode URLs to download.",
    )
    parser.add_argument(
        "-m",
        "--missing",
        action="store_true",
        help="Re-download archive-marked files missing locally.",
    )
    parser.add_argument(
        "--log",
        nargs="?",
        const="__enable__",
        default=None,
        help="Enable run logging, optionally to a specific path.",
    )
    parser.add_argument(
        "--debug-pids",
        action="store_true",
        help="Log worker and yt-dlp PID transitions.",
    )
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="Refresh the per-show metadata cache.",
    )
    parser.add_argument(
        "--clear-metadata-cache",
        action="store_true",
        help="Delete the per-show metadata cache before refresh.",
    )
    parser.add_argument(
        "--metadata-max-age-hours",
        type=int,
        default=None,
        help="Maximum metadata cache age in hours.",
    )
    parser.add_argument(
        "--rss",
        dest="rss",
        action="store_true",
        help="Generate `feed.xml` after the download run.",
    )
    parser.add_argument(
        "--no-rss",
        dest="rss",
        action="store_false",
        help="Disable RSS generation.",
    )
    parser.set_defaults(rss=None)
    parser.add_argument(
        "--rss-base-url",
        default=None,
        help="Public base URL used for RSS enclosure links.",
    )
    parser.add_argument(
        "--playlist",
        dest="playlist",
        action="store_true",
        help="Generate `playlist.m3u` after the download run.",
    )
    parser.add_argument(
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
    sources_override, groups, non_season_groups = discover_grouped_episode_sources(
        slug,
        selected_seasons,
        request_all,
    )
    slug, program_url, episodes, summary, metadata_cache_file = load_show_context(
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
    if summary.has_seasons:
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
    if archived_ids:
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
        if missing_archived_ids and settings.auto_redownload_missing:
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
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    downloader: Downloader | None = None
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        with progress:
            overall_label = f"[bold]Total ({len(filtered)} episode(s))[/bold]"
            overall = progress.add_task(overall_label, total=len(filtered))
            downloader = Downloader(
                archive_file=archive_file,
                output_template=output_template,
                audio_format=settings.audio_format,
                log_file=log_file,
                rich_progress=progress,
                debug_pids=settings.debug_pids,
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
                    task_id=progress.add_task(f"download {episode.label}", total=100),
                )
                for episode in filtered
            ]
            done_count = skip_count = error_count = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=settings.jobs) as executor:
                download_futures: dict[
                    concurrent.futures.Future[tuple[str, str]],
                    DownloadTask,
                ] = {executor.submit(downloader.download_one, task): task for task in tasks}
                for future in concurrent.futures.as_completed(download_futures):
                    state, _detail = future.result()
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
    if "--version" in argv:
        console.print(f"raiplaysound-cli {__version__}")
        return 0
    if "-h" in argv or "--help" in argv:
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
                return list_stations(settings, args)
            if target == "programs":
                return list_programs(settings, args)
            if target == "seasons":
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
