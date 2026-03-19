from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path

from .errors import CLIError
from .models import Episode, GroupSource, GroupSummary, SeasonSummary
from .runtime import http_get, run_yt_dlp

PROGRAM_URL_RE = re.compile(r"^https?://www\.raiplaysound\.it/programmi/([A-Za-z0-9-]+)/?$")
PROGRAM_SLUG_RE = re.compile(r"^[A-Za-z0-9-]+$")
EPISODE_URL_RE = re.compile(r"^https?://www\.raiplaysound\.it/.+")
SEASON_PAGE_RE = re.compile(
    r"/programmi/(?P<slug>[A-Za-z0-9-]+)/(?P<section>episodi|puntate)/stagione-(?P<season>\d+)"
)
GROUP_LINK_RE = re.compile(
    r'<a href="(?P<href>/programmi/(?P<slug>[A-Za-z0-9-]+)/'
    r'(?P<section>[^"/]+)/(?P<tail>[^"]+))"[^>]*>'
    r"(?P<label>[^<]+)</a>"
)
EPISODE_ID_FROM_URL_RE = re.compile(r"-([0-9a-fA-F-]{8,})\.(?:html|json)$")
SEASON_IN_TITLE_RE = re.compile(r"[Ss](\d{1,3})[ _-]*[Ee]\d{1,3}")
SEASON_LABEL_RE = re.compile(
    r"(?:\bStagione\s+(\d{1,3})\b|\b(\d{1,3})\s*\^?\s*Stagione\b)",
    re.IGNORECASE,
)
CURRENT_FILTER_LABEL_RE = re.compile(
    r"data-filters-current[^>]*>.*?<span[^>]*>(?P<label>[^<]+)</span>",
    re.IGNORECASE | re.DOTALL,
)
SKIP_GROUP_SECTIONS = {"clip", "extra", "playlist", "novita"}


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


def _normalize_group_token(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized


def build_requested_groups(raw: str) -> set[str]:
    selected: set[str] = set()
    if not raw:
        return selected
    for part in [item.strip() for item in raw.split(",") if item.strip()]:
        token = _normalize_group_token(part)
        if not token:
            raise CLIError(f"invalid group '{part}'.")
        selected.add(token)
    return selected


def discover_feed_sources(
    slug: str,
    selected_seasons: set[str],
    include_all_seasons: bool,
    for_list_seasons: bool,
) -> list[str]:
    program_url = f"https://www.raiplaysound.it/programmi/{slug}"
    html = http_get(program_url)
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


def discover_season_listing_sources(slug: str) -> tuple[str, list[str]]:
    program_url = f"https://www.raiplaysound.it/programmi/{slug}"
    html = http_get(program_url)
    linked_matches = [
        match
        for match in SEASON_PAGE_RE.finditer(html)
        if match.group("slug").lower() == slug.lower()
    ]
    season_urls = {f"https://www.raiplaysound.it{match.group(0)}" for match in linked_matches}
    known_numbers = {int(match.group("season")) for match in linked_matches}
    for label_match in SEASON_LABEL_RE.findall(html):
        for value in label_match:
            if value:
                known_numbers.add(int(value))
    linked_sections = {match.group("section") for match in linked_matches}
    sections = linked_sections or {"episodi", "puntate"}
    if known_numbers and not linked_matches:
        for section in sections:
            for season in range(1, max(known_numbers) + 1):
                candidate = f"{program_url}/{section}/stagione-{season}"
                try:
                    http_get(candidate)
                except Exception:
                    continue
                season_urls.add(candidate)
    for section in sections:
        for season in sorted(known_numbers):
            candidate = f"{program_url}/{section}/stagione-{season}"
            if linked_sections:
                season_urls.add(candidate)
                continue
            try:
                http_get(candidate)
            except Exception:
                continue
            season_urls.add(candidate)
    next_number = max(known_numbers) + 1 if known_numbers else 1
    while True:
        found_next = False
        for section in sections:
            candidate = f"{program_url}/{section}/stagione-{next_number}"
            try:
                http_get(candidate)
            except Exception:
                continue
            season_urls.add(candidate)
            found_next = True
        if not found_next:
            break
        next_number += 1
    if season_urls:
        return program_url, sorted(season_urls)
    return program_url, [program_url]


def _normalize_group_label(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _classify_group(section: str, tail: str, label: str) -> tuple[str, str] | None:
    normalized_section = section.lower()
    normalized_tail = tail.strip("/").lower()
    normalized_label = label.lower()
    if normalized_section in SKIP_GROUP_SECTIONS:
        return None
    if normalized_section == "speciali":
        return "special", tail
    if normalized_section == "puntate-e-podcast":
        return "series", tail
    if normalized_section.startswith("episodi") or normalized_section.startswith("puntate"):
        if normalized_tail.startswith("stagione-"):
            return "season", normalized_tail.removeprefix("stagione-")
        if normalized_tail in {"episodi", "puntate"}:
            if "stagione" in normalized_label:
                return "season", normalized_label
            return None
        return "bucket", tail
    return None


def discover_group_listing_sources(slug: str) -> tuple[str, list[GroupSource]]:
    program_url = f"https://www.raiplaysound.it/programmi/{slug}"
    html_text = http_get(program_url)
    groups: list[GroupSource] = []
    seen_urls: set[str] = set()
    linked_groups: list[GroupSource] = []

    for match in GROUP_LINK_RE.finditer(html_text):
        if match.group("slug").lower() != slug.lower():
            continue
        label = _normalize_group_label(match.group("label"))
        href = f"https://www.raiplaysound.it{match.group('href').rstrip('/')}"
        classified = _classify_group(match.group("section"), match.group("tail"), label)
        if classified is None or href in seen_urls:
            continue
        kind, key = classified
        linked_groups.append(
            GroupSource(
                key=key,
                label=label,
                url=href,
                kind=kind,
            )
        )
        seen_urls.add(href)

    current_match = CURRENT_FILTER_LABEL_RE.search(html_text)
    current_label = _normalize_group_label(current_match.group("label")) if current_match else ""
    if current_label and linked_groups:
        first_group = linked_groups[0]
        current_kind = first_group.kind
        current_key = _normalize_group_token(current_label)
        if current_kind == "season":
            season_match = re.search(r"(\d{1,3})", current_label)
            if season_match:
                current_key = season_match.group(1)
        current_group = GroupSource(
            key=current_key,
            label=current_label,
            url=program_url,
            kind=current_kind,
        )
        if all(group.label != current_group.label for group in linked_groups):
            groups.append(current_group)

    groups.extend(linked_groups)
    if groups:
        return program_url, groups

    season_url_program, season_urls = discover_season_listing_sources(slug)
    if season_urls != [program_url]:
        season_groups: list[GroupSource] = []
        for url in season_urls:
            season_match = re.search(r"stagione-(\d+)$", url)
            if season_match:
                season_number = season_match.group(1)
                season_groups.append(
                    GroupSource(
                        key=season_number,
                        label=f"Stagione {season_number}",
                        url=url,
                        kind="season",
                    )
                )
        if season_groups:
            season_groups.sort(key=lambda group: int(group.key))
            return season_url_program, season_groups

    return program_url, []


def discover_grouped_episode_sources(
    slug: str,
    selected_seasons: set[str],
    include_all_seasons: bool,
    selected_groups: set[str],
) -> tuple[list[str] | None, list[GroupSource] | None, bool]:
    _program_url, groups = discover_group_listing_sources(slug)
    requested_groups = selected_groups
    if requested_groups and (selected_seasons or include_all_seasons):
        raise CLIError("--season and --group cannot be used together.")
    if not groups:
        if requested_groups:
            raise CLIError("this program does not expose groupings, so --group cannot be used.")
        return None, None, False
    all_seasons = all(group.kind == "season" for group in groups)
    if all_seasons and requested_groups:
        raise CLIError("this program exposes seasons, so use --season instead of --group.")
    if not all_seasons and (selected_seasons or include_all_seasons):
        raise CLIError("this program does not expose seasons, so --season cannot be used.")
    selected_sources: list[GroupSource] = list(groups)
    if all_seasons and selected_seasons and not include_all_seasons:
        available_seasons = {group.key for group in groups}
        missing = sorted(selected_seasons - available_seasons, key=int)
        if missing:
            raise CLIError(f"season {missing[0]} is not available.")
        selected_sources = [group for group in groups if group.key in selected_seasons]
    elif requested_groups:
        available: dict[str, GroupSource] = {}
        for group in groups:
            for candidate in {
                _normalize_group_token(group.key),
                _normalize_group_token(group.label),
            }:
                if candidate:
                    available[candidate] = group
        missing = sorted(requested_groups - set(available))
        if missing:
            raise CLIError(f"group '{missing[0]}' is not available.")
        selected_sources = []
        seen_urls: set[str] = set()
        for request in sorted(requested_groups):
            group = available[request]
            if group.url in seen_urls:
                continue
            selected_sources.append(group)
            seen_urls.add(group.url)
    return [group.url for group in selected_sources], selected_sources, not all_seasons


def collect_episodes_from_sources(
    sources: list[str],
    source_groups: dict[str, GroupSource] | None = None,
) -> list[Episode]:
    seen: dict[str, Episode] = {}
    episodes: list[Episode] = []
    for source in sources:
        season_hint = ""
        match = re.search(r"stagione-(\d+)$", source)
        if match:
            season_hint = match.group(1)
        group_source = source_groups.get(source) if source_groups is not None else None
        result = run_yt_dlp(
            [
                "--flat-playlist",
                "--ignore-errors",
                "--print",
                "%(id)s\t%(webpage_url)s",
                source,
            ],
            allow_partial_failure=True,
        )
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            episode_id = parts[0].strip()
            episode_url = parts[1].strip().rstrip("/")
            if not episode_id or not episode_url:
                continue
            existing = seen.get(episode_id)
            if existing is not None:
                if not existing.season and season_hint:
                    existing.season = season_hint
                if not existing.group_label and group_source is not None:
                    existing.group_label = group_source.label
                    existing.group_kind = group_source.kind
                continue
            base_name = Path(urllib.parse.urlparse(episode_url).path).stem
            label = re.sub(rf"-{re.escape(episode_id)}$", "", base_name) or episode_id
            episode = Episode(
                episode_id=episode_id,
                url=episode_url,
                label=label,
                season=season_hint,
                group_label=group_source.label if group_source is not None else "",
                group_kind=group_source.kind if group_source is not None else "",
            )
            seen[episode_id] = episode
            episodes.append(episode)
    if not episodes:
        raise CLIError("No episodes found.")
    return episodes


def collect_season_summary_from_sources(sources: list[str]) -> tuple[list[Episode], SeasonSummary]:
    episodes = collect_episodes_from_sources(sources)
    season_counts: dict[str, int] = {}
    season_year_min: dict[str, str] = {}
    season_year_max: dict[str, str] = {}
    show_year_min = ""
    show_year_max = ""
    explicit_seasons = any("stagione-" in source for source in sources)

    for episode in episodes:
        season = episode.season if episode.season.isdigit() else "1"
        episode.season = season
        episode.year = extract_year_from_url(episode.url)
        season_counts[season] = season_counts.get(season, 0) + 1
        if re.fullmatch(r"\d{4}", episode.year):
            if not show_year_min or episode.year < show_year_min:
                show_year_min = episode.year
            if not show_year_max or episode.year > show_year_max:
                show_year_max = episode.year
            current_min = season_year_min.get(season)
            current_max = season_year_max.get(season)
            if current_min is None or episode.year < current_min:
                season_year_min[season] = episode.year
            if current_max is None or episode.year > current_max:
                season_year_max[season] = episode.year

    latest_season = (
        sorted(season_counts, key=lambda value: int(value))[-1] if season_counts else "1"
    )
    return episodes, SeasonSummary(
        counts=season_counts,
        year_min=season_year_min,
        year_max=season_year_max,
        show_year_min=show_year_min,
        show_year_max=show_year_max,
        has_seasons=explicit_seasons or len(season_counts) > 1,
        latest_season=latest_season,
    )


def collect_group_summaries(groups: list[GroupSource]) -> list[GroupSummary]:
    summaries: list[GroupSummary] = []
    for group in groups:
        episodes = collect_episodes_from_sources([group.url])
        year_min = ""
        year_max = ""
        for episode in episodes:
            episode.year = extract_year_from_url(episode.url)
            if re.fullmatch(r"\d{4}", episode.year):
                if not year_min or episode.year < year_min:
                    year_min = episode.year
                if not year_max or episode.year > year_max:
                    year_max = episode.year
        summaries.append(
            GroupSummary(
                key=group.key,
                label=group.label,
                url=group.url,
                kind=group.kind,
                episodes=len(episodes),
                year_min=year_min,
                year_max=year_max,
            )
        )
    return summaries


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


def _episode_json_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized.endswith(".json"):
        return normalized
    if normalized.endswith(".html"):
        return normalized[:-5] + ".json"
    return normalized + ".json"


def _normalize_episode_upload_date(payload: dict[str, object]) -> str:
    date_tracking = str(payload.get("date_tracking") or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_tracking)
    if match:
        return "".join(match.groups())
    create_date = str(payload.get("create_date") or "").strip()
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", create_date)
    if match:
        day, month, year = match.groups()
        return f"{year}{month}{day}"
    return "NA"


def _collect_metadata_from_episode_json(source: str) -> dict[str, tuple[str, str, str]]:
    payload = json.loads(http_get(_episode_json_url(source)))
    if not isinstance(payload, dict):
        raise CLIError("invalid episode payload")
    raw_id = str(payload.get("uniquename") or "")
    match = re.search(r"ContentItem-([0-9a-fA-F-]{8,})$", raw_id)
    if match:
        episode_id = match.group(1)
    else:
        path_id = str(payload.get("path_id") or payload.get("weblink") or "")
        match = EPISODE_ID_FROM_URL_RE.search(path_id)
        if not match:
            raise CLIError("episode metadata did not include an ID")
        episode_id = match.group(1)
    title = str(payload.get("title") or payload.get("episode_title") or "NA")
    season = str(payload.get("season") or payload.get("season_number") or "NA")
    return {episode_id: (_normalize_episode_upload_date(payload), season, title)}


def collect_metadata(
    sources: list[str], *, single_entries: bool = False
) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for source in sources:
        if single_entries:
            try:
                result.update(_collect_metadata_from_episode_json(source))
                continue
            except Exception:
                pass
        args = [
            "--skip-download",
            "--ignore-errors",
            "--print",
            "%(id)s\t%(upload_date|NA)s\t%(title|NA)s\t%(season_number|NA)s",
        ]
        if single_entries:
            args.append("--no-playlist")
        metadata = run_yt_dlp(
            args + [source],
            allow_partial_failure=True,
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


def cache_entry_is_complete(entry: tuple[str, str, str] | None) -> bool:
    if entry is None:
        return False
    upload, _season, title = entry
    return bool(upload and upload != "NA" and title and title != "NA")


def normalize_episode_metadata(
    episodes: list[Episode],
    metadata: dict[str, tuple[str, str, str]],
) -> SeasonSummary:
    season_counts: dict[str, int] = {}
    season_year_min: dict[str, str] = {}
    season_year_max: dict[str, str] = {}
    show_year_min = ""
    show_year_max = ""
    detected_season_evidence = False
    for episode in episodes:
        upload_date, meta_season, title = metadata.get(
            episode.episode_id,
            ("NA", "NA", episode.label.replace("-", " ")),
        )
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
        if re.fullmatch(r"\d{8}", episode.upload_date):
            episode.year = episode.upload_date[:4]
        else:
            episode.year = extract_year_from_url(episode.url)
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
    latest_season = (
        sorted(season_counts, key=lambda value: int(value))[-1] if season_counts else "1"
    )
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
        requested_url_ids = {value for value in requested_episode_urls.values() if value}
        for episode in selected:
            include = False
            normalized = episode.url.rstrip("/")
            if episode.episode_id in requested_episode_ids:
                include = True
                matched_ids.add(episode.episode_id)
            if normalized in requested_episode_urls:
                include = True
                matched_urls.add(normalized)
            if episode.episode_id in requested_url_ids:
                include = True
                for requested_url, extracted_id in requested_episode_urls.items():
                    if extracted_id == episode.episode_id:
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
