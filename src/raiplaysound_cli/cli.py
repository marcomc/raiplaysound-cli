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
from .downloads import Downloader, DownloadTask, remove_missing_ids_from_archive, resolve_log_file
from .episodes import (
    build_requested_episode_filters,
    build_requested_set,
    cache_entry_is_complete,
    collect_episodes_from_sources,
    collect_metadata,
    detect_slug,
    discover_feed_sources,
    filter_episodes_for_list_or_download,
    load_metadata_cache,
    normalize_episode_metadata,
    write_metadata_cache,
    year_span,
)
from .errors import CLIError
from .models import Episode
from .outputs import generate_playlist, generate_rss_feed
from .runtime import acquire_lock, http_get, release_lock, run_yt_dlp

console = Console()
err_console = Console(stderr=True)


def json_dump(data: Any) -> None:
    console.print(json.dumps(data, indent=2, ensure_ascii=False))


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


def load_show_context(
    settings: Settings,
    input_value: str,
    selected_seasons: set[str],
    request_all_seasons: bool,
    *,
    for_list_seasons: bool = False,
) -> tuple[str, str, list[Any], Any, Path]:
    slug, program_url = detect_slug(input_value)
    target_dir = settings.target_base / slug
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    sources = discover_feed_sources(
        slug,
        selected_seasons,
        request_all_seasons,
        for_list_seasons,
    )
    episodes = collect_episodes_from_sources(sources)
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
    return 0


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
            seasons.append(
                {
                    "season": "1",
                    "episodes": len(episodes),
                    "published": year_span(summary.show_year_min, summary.show_year_max),
                }
            )
        else:
            for season in sorted(summary.counts, key=lambda item: int(item)):
                seasons.append(
                    {
                        "season": season,
                        "episodes": summary.counts[season],
                        "published": year_span(
                            summary.year_min.get(season, ""),
                            summary.year_max.get(season, ""),
                        ),
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
        console.print(
            f"  - Episodes: {len(episodes)} "
            f"(published: {year_span(summary.show_year_min, summary.show_year_max)})"
        )
        return 0
    console.print(f"Available seasons for {slug} ({program_url}):")
    for season in sorted(summary.counts, key=lambda item: int(item)):
        published = year_span(
            summary.year_min.get(season, ""),
            summary.year_max.get(season, ""),
        )
        console.print(
            f"  - Season {season}: {summary.counts[season]} episodes " f"(published: {published})"
        )
    return 0


def list_episodes(settings: Settings, args: argparse.Namespace) -> int:
    selected_seasons, request_all = build_requested_set(args.season or settings.seasons_arg)
    slug, program_url, episodes, summary, _metadata_cache = load_show_context(
        settings,
        args.input,
        selected_seasons,
        request_all,
    )
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
    if settings.list_target and not any(
        (args.stations, args.programs, args.seasons, args.episodes)
    ):
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
    slug, program_url, episodes, summary, metadata_cache_file = load_show_context(
        settings,
        args.input or settings.input_value,
        selected_seasons,
        request_all,
    )
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
    if "--version" in argv:
        console.print(f"raiplaysound-cli {__version__}")
        return 0
    if "-h" in argv or "--help" in argv:
        command, _rest = choose_command(
            [arg for arg in argv if arg not in {"-h", "--help"}],
            parse_env_file(Path.home() / ".raiplaysound-cli.conf"),
        )
        parser = build_list_parser() if command == "list" else build_download_parser()
        parser.print_help()
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
            else:
                target = (
                    "stations"
                    if args.stations
                    else (
                        "programs"
                        if args.programs
                        else "seasons" if args.seasons else "episodes" if args.episodes else ""
                    )
                )
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
                raise CLIError(
                    "list mode requires exactly one target: "
                    "--stations, --programs, --seasons, or --episodes."
                )
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
