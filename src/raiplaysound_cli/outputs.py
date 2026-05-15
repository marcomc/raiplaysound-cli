from __future__ import annotations

import calendar
import email.utils
import html
import json
import re
import time
import urllib.parse
from importlib import resources
from pathlib import Path

from .catalog import fetch_program_details, fetch_program_metadata
from .episodes import load_metadata_cache
from .models import ProgramDetails
from .runtime import http_get_bytes

DATE_IN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
PROGRAM_INFO_FILE = ".program-info.json"
ARTWORK_STEM = "cover"
INDEX_ICON_FILE = "apple-touch-icon.png"
INDEX_ICON_URL = "https://www.raiplaysound.it/assets/img/icons/apple/apple-touch-icon.png"
INDEX_ICON_RESOURCE_PACKAGE = "raiplaysound_cli.assets"
TITLE_SEPARATOR_RE = re.compile(r"^.*\d{4}-\d{2}-\d{2}\s+-\s+")
TitleEntry = tuple[str, str, str]


def _url_for_artifact(path: Path, slug: str, base_url: str) -> str:
    if base_url:
        return f"{base_url.rstrip('/')}/{slug}/{urllib.parse.quote(path.name)}"
    return path.resolve().as_uri()


def fetch_show_title(slug: str) -> str:
    program = fetch_program_metadata(slug)
    return program.title if program else slug


def fallback_program_details(slug: str, program_url: str) -> ProgramDetails:
    return ProgramDetails(
        slug=slug,
        title=fetch_show_title(slug),
        author="RAI Play Sound",
        description="",
        page_url=program_url,
        image_url="",
    )


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


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


def image_suffix_for_type(url: str, content_type: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(content_type, ".jpg")


def load_program_details(path: Path) -> ProgramDetails | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    slug = str(payload.get("slug") or path.parent.name)
    return ProgramDetails(
        slug=slug,
        title=str(payload.get("title") or slug),
        author=str(payload.get("author") or "RAI Play Sound"),
        description=str(payload.get("description") or ""),
        page_url=str(payload.get("page_url") or f"https://www.raiplaysound.it/programmi/{slug}"),
        image_url=str(payload.get("image_url") or ""),
        artwork_file=str(payload.get("artwork_file") or ""),
    )


def write_program_details(target_dir: Path, details: ProgramDetails) -> Path:
    path = target_dir / PROGRAM_INFO_FILE
    path.write_text(
        json.dumps(
            {
                "slug": details.slug,
                "title": details.title,
                "author": details.author,
                "description": details.description,
                "page_url": details.page_url,
                "image_url": details.image_url,
                "artwork_file": details.artwork_file,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def download_program_artwork(target_dir: Path, details: ProgramDetails) -> ProgramDetails:
    if not details.image_url:
        return details
    try:
        raw, content_type = http_get_bytes(details.image_url, timeout=30.0)
    except Exception:
        return details
    suffix = image_suffix_for_type(details.image_url, content_type)
    artwork_path = target_dir / f"{ARTWORK_STEM}{suffix}"
    artwork_path.write_bytes(raw)
    for old_path in target_dir.glob(f"{ARTWORK_STEM}.*"):
        if old_path != artwork_path and old_path.suffix.lower() in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            old_path.unlink(missing_ok=True)
    details.artwork_file = artwork_path.name
    return details


def _merge_program_details(
    preferred: ProgramDetails, cached: ProgramDetails | None
) -> ProgramDetails:
    if cached is None:
        return preferred
    return ProgramDetails(
        slug=preferred.slug or cached.slug,
        title=preferred.title or cached.title,
        author=preferred.author or cached.author,
        description=preferred.description or cached.description,
        page_url=preferred.page_url or cached.page_url,
        image_url=preferred.image_url or cached.image_url,
        artwork_file=preferred.artwork_file or cached.artwork_file,
    )


def prepare_program_assets(target_dir: Path, slug: str, program_url: str) -> ProgramDetails:
    cached_details = load_program_details(target_dir / PROGRAM_INFO_FILE)
    fetched_details = fetch_program_details(slug)
    if fetched_details is not None:
        details = _merge_program_details(fetched_details, cached_details)
    elif cached_details is not None:
        details = cached_details
    else:
        details = fallback_program_details(slug, program_url)
    details = download_program_artwork(target_dir, details)
    write_program_details(target_dir, details)
    return details


def ensure_program_assets(target_dir: Path, slug: str) -> ProgramDetails:
    program_url = f"https://www.raiplaysound.it/programmi/{slug}"
    details = load_program_details(target_dir / PROGRAM_INFO_FILE)
    artwork_path = target_dir / details.artwork_file if details and details.artwork_file else None
    if details is not None and artwork_path is not None and artwork_path.exists():
        return details
    if details is None or not details.image_url:
        details = (
            fetch_program_details(slug) or details or fallback_program_details(slug, program_url)
        )
    details = download_program_artwork(target_dir, details)
    write_program_details(target_dir, details)
    return details


def download_index_icon(target_base: Path) -> Path | None:
    icon_path = target_base / INDEX_ICON_FILE
    try:
        icon_resource = resources.files(INDEX_ICON_RESOURCE_PACKAGE).joinpath(INDEX_ICON_FILE)
        icon_path.write_bytes(icon_resource.read_bytes())
        return icon_path
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        pass
    try:
        raw, _content_type = http_get_bytes(INDEX_ICON_URL, timeout=30.0)
    except Exception:
        return icon_path if icon_path.exists() else None
    icon_path.write_bytes(raw)
    return icon_path


def _local_audio_entries(target_dir: Path) -> list[tuple[str, Path]] | None:
    entries: list[tuple[str, Path]] = []
    try:
        file_paths = list(target_dir.iterdir())
    except OSError:
        return None
    for file_path in file_paths:
        if not file_path.is_file() or file_path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        match = DATE_IN_NAME_RE.search(file_path.name)
        if match:
            entries.append((match.group(1), file_path))
    return entries


def _metadata_date(upload_date: str) -> str | None:
    if not re.fullmatch(r"\d{8}", upload_date):
        return None
    return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"


def _filename_title(file_path: Path) -> str:
    return TITLE_SEPARATOR_RE.sub("", file_path.stem)


def _title_key(title: str) -> str:
    return " ".join(title.replace("\u29f8", "/").split()).casefold()


def _store_unique_title_entry(
    cache_by_title: dict[str, TitleEntry | None],
    title: str,
    entry: TitleEntry,
) -> None:
    key = _title_key(title)
    if key in cache_by_title:
        cache_by_title[key] = None
    else:
        cache_by_title[key] = entry


def _metadata_cache_indexes(
    metadata_cache_file: Path,
) -> tuple[dict[str, list[TitleEntry]], dict[str, TitleEntry | None]]:
    cache_by_date: dict[str, list[TitleEntry]] = {}
    cache_by_title: dict[str, TitleEntry | None] = {}
    for episode_id, metadata in load_metadata_cache(metadata_cache_file).items():
        metadata_date = _metadata_date(metadata.upload_date)
        if metadata_date is None:
            continue
        entry = (metadata.title, episode_id, metadata_date)
        cache_by_date.setdefault(metadata_date, []).append(entry)
        _store_unique_title_entry(cache_by_title, metadata.title, entry)
    return cache_by_date, cache_by_title


def _audio_entry_dates(
    audio_entries: list[tuple[str, Path]],
    metadata_cache_file: Path,
) -> list[str]:
    cache_by_date, cache_by_title = _metadata_cache_indexes(metadata_cache_file)
    audio_count_by_date: dict[str, int] = {}
    audio_count_by_title: dict[str, int] = {}
    for file_date, _file_path in audio_entries:
        audio_count_by_date[file_date] = audio_count_by_date.get(file_date, 0) + 1
    for _file_date, file_path in audio_entries:
        title_key = _title_key(_filename_title(file_path))
        audio_count_by_title[title_key] = audio_count_by_title.get(title_key, 0) + 1

    dates: list[str] = []
    for file_date, file_path in audio_entries:
        dated_entries = cache_by_date.get(file_date, [])
        filename_title_key = _title_key(_filename_title(file_path))
        title_entry = cache_by_title.get(filename_title_key)
        if title_entry is not None and audio_count_by_title.get(filename_title_key) == 1:
            _title, _guid, metadata_date = title_entry
            dates.append(metadata_date)
        elif len(dated_entries) == 1 and audio_count_by_date.get(file_date, 0) == 1:
            _title, _guid, metadata_date = dated_entries[0]
            dates.append(metadata_date)
        else:
            dates.append(file_date)
    return dates


def generate_rss_feed(
    target_dir: Path,
    slug: str,
    program_url: str,
    metadata_cache_file: Path,
    base_url: str,
    details: ProgramDetails | None = None,
) -> Path:
    cache_by_date, cache_by_title = _metadata_cache_indexes(metadata_cache_file)
    details = details or load_program_details(target_dir / PROGRAM_INFO_FILE)
    if details is None:
        details = fetch_program_details(slug) or fallback_program_details(slug, program_url)
    show_title = details.title
    artwork_path = target_dir / details.artwork_file if details.artwork_file else None
    artwork_url = (
        _url_for_artifact(artwork_path, slug, base_url)
        if artwork_path is not None and artwork_path.exists()
        else ""
    )
    items_by_guid: dict[str, tuple[int, str, str, str, str, str, str, int]] = {}
    audio_entries = _local_audio_entries(target_dir) or []
    audio_count_by_date: dict[str, int] = {}
    audio_count_by_title: dict[str, int] = {}
    for file_date, _file_path in audio_entries:
        audio_count_by_date[file_date] = audio_count_by_date.get(file_date, 0) + 1
    for _file_date, file_path in audio_entries:
        title_key = _title_key(_filename_title(file_path))
        audio_count_by_title[title_key] = audio_count_by_title.get(title_key, 0) + 1
    for file_date, file_path in sorted(audio_entries, reverse=True):
        dated_entries = cache_by_date.get(file_date, [])
        filename_title = _filename_title(file_path)
        filename_title_key = _title_key(filename_title)
        title_entry = cache_by_title.get(filename_title_key)
        if title_entry is not None and audio_count_by_title.get(filename_title_key) == 1:
            title, guid, metadata_date = title_entry
            publish_date = metadata_date
        elif len(dated_entries) == 1 and audio_count_by_date.get(file_date, 0) == 1:
            title, guid, publish_date = dated_entries[0]
        else:
            title = filename_title
            guid = file_path.stem
            publish_date = file_date
        enclosure = _url_for_artifact(file_path, slug, base_url)
        published_at = calendar.timegm(time.strptime(publish_date, "%Y-%m-%d"))
        item = (
            file_path.stat().st_mtime_ns,
            title,
            guid,
            email.utils.formatdate(
                published_at,
                usegmt=True,
            ),
            enclosure,
            str(file_path.stat().st_size),
            media_type_for_suffix(file_path),
            published_at,
        )
        existing = items_by_guid.get(guid)
        if existing is None or item[0] >= existing[0]:
            items_by_guid[guid] = item
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        "  <channel>",
        f"    <title>{xml_escape(show_title)}</title>",
        f"    <link>{xml_escape(program_url)}</link>",
        f"    <description>{xml_escape(details.description or show_title)}</description>",
        "    <language>it</language>",
        f"    <itunes:title>{xml_escape(show_title)}</itunes:title>",
        f"    <itunes:author>{xml_escape(details.author)}</itunes:author>",
        "    <itunes:explicit>false</itunes:explicit>",
    ]
    if artwork_url:
        lines.extend(
            [
                "    <image>",
                f"      <url>{xml_escape(artwork_url)}</url>",
                f"      <title>{xml_escape(show_title)}</title>",
                f"      <link>{xml_escape(program_url)}</link>",
                "    </image>",
                f'    <itunes:image href="{xml_escape(artwork_url)}"/>',
            ]
        )
    items = sorted(
        items_by_guid.values(),
        key=lambda item: (item[7], item[2]),
        reverse=True,
    )
    for item in items:
        _mtime_ns, title, guid, pub_date, enclosure, size, mime, _published_at = item
        enclosure_tag = (
            f'      <enclosure url="{xml_escape(enclosure)}" '
            f'length="{size}" type="{xml_escape(mime)}"/>'
        )
        lines.extend(
            [
                "    <item>",
                f"      <title>{xml_escape(title)}</title>",
                f"      <link>{xml_escape(program_url)}</link>",
                f'      <guid isPermaLink="false">{xml_escape(guid)}</guid>',
                f"      <pubDate>{pub_date}</pubDate>",
                enclosure_tag,
                "    </item>",
            ]
        )
    lines.extend(["  </channel>", "</rss>"])
    feed_path = target_dir / "feed.xml"
    feed_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return feed_path


def generate_playlist(target_dir: Path, metadata_cache_file: Path) -> Path:
    cache_by_date: dict[str, list[str]] = {}
    cache_by_title: dict[str, str | None] = {}
    for _episode_id, metadata in load_metadata_cache(metadata_cache_file).items():
        metadata_date = _metadata_date(metadata.upload_date)
        if metadata_date is None:
            continue
        cache_by_date.setdefault(metadata_date, []).append(metadata.title)
        key = _title_key(metadata.title)
        if key in cache_by_title:
            cache_by_title[key] = None
        else:
            cache_by_title[key] = metadata.title
    entries: list[tuple[str, Path]] = []
    entries.extend(_local_audio_entries(target_dir) or [])
    entries.sort(key=lambda item: item[0])
    lines = ["#EXTM3U"]
    for file_date, file_path in entries:
        filename_title = _filename_title(file_path)
        title_by_name = cache_by_title.get(_title_key(filename_title))
        dated_titles = cache_by_date.get(file_date, [])
        if title_by_name is not None:
            title = title_by_name
        elif len(dated_titles) == 1:
            title = dated_titles[0]
        else:
            title = filename_title
        lines.append(f"#EXTINF:-1,{title}")
        lines.append(file_path.name)
    playlist_path = target_dir / "playlist.m3u"
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist_path


def _program_index_item(show_dir: Path, base_url: str) -> dict[str, str | int] | None:
    slug = show_dir.name
    audio_entries = _local_audio_entries(show_dir)
    if audio_entries is None or not audio_entries:
        return None
    try:
        details = ensure_program_assets(show_dir, slug)
    except OSError:
        return None
    latest_date = max(
        _audio_entry_dates(audio_entries, show_dir / ".metadata-cache.tsv"), default=""
    )
    artwork_path = show_dir / details.artwork_file if details.artwork_file else None
    feed_path = show_dir / "feed.xml"
    folder_href = f"{urllib.parse.quote(show_dir.name)}/"
    feed_href = (
        f"{base_url.rstrip('/')}/{urllib.parse.quote(show_dir.name)}/feed.xml"
        if base_url
        else f"{urllib.parse.quote(show_dir.name)}/feed.xml"
    )
    artwork_href = (
        f"{urllib.parse.quote(show_dir.name)}/{urllib.parse.quote(artwork_path.name)}"
        if artwork_path is not None and artwork_path.exists()
        else ""
    )
    return {
        "slug": slug,
        "title": details.title,
        "author": details.author,
        "description": details.description,
        "folder_href": folder_href,
        "feed_href": feed_href if _path_exists(feed_path) else "",
        "artwork_href": artwork_href,
        "episode_count": len(audio_entries),
        "latest_date": latest_date,
    }


def _iter_program_dirs(target_base: Path) -> list[Path]:
    program_dirs: list[Path] = []
    for show_dir in sorted(target_base.iterdir(), key=lambda item: item.name.casefold()):
        if show_dir.name.startswith("."):
            continue
        try:
            if not show_dir.is_dir():
                continue
        except OSError:
            continue
        program_dirs.append(show_dir)
    return program_dirs


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def generate_program_index(target_base: Path, base_url: str = "") -> Path:
    target_base.mkdir(parents=True, exist_ok=True)
    icon_path = download_index_icon(target_base)
    icon_href = urllib.parse.quote(icon_path.name) if icon_path is not None else ""
    items = [
        item
        for show_dir in _iter_program_dirs(target_base)
        for item in [_program_index_item(show_dir, base_url)]
        if item is not None
    ]
    rows = []
    for item in items:
        folder_href = html.escape(str(item["folder_href"]), quote=True)
        title = html.escape(str(item["title"]))
        author = html.escape(str(item["author"]))
        description = html.escape(str(item["description"]) or "Descrizione non disponibile.")
        image = (
            f'<img src="{html.escape(str(item["artwork_href"]), quote=True)}" '
            f'alt="{html.escape(str(item["title"]), quote=True)}">'
            if item["artwork_href"]
            else '<div class="cover-placeholder" aria-hidden="true"></div>'
        )
        feed = (
            f'<a class="feed" href="{html.escape(str(item["feed_href"]), quote=True)}">RSS</a>'
            if item["feed_href"]
            else ""
        )
        latest = str(item["latest_date"] or "Nessun episodio locale")
        rows.append(
            '      <article class="program-row">'
            f'<a class="cover" href="{folder_href}">'
            f"{image}</a>"
            '<div class="program-copy">'
            f'<a class="program-title" href="{folder_href}">'
            f"{title}</a>"
            f'<p class="program-author">{author}</p>'
            f'<p class="program-description">{description}</p>'
            '<div class="program-meta">'
            f"<span>{item['episode_count']} episodi</span>"
            f"<span>Ultimo: {html.escape(latest)}</span>"
            f"{feed}"
            "</div>"
            "</div>"
            "</article>"
        )
    title_icon = (
        f'<img class="app-icon" src="{icon_href}" alt="" aria-hidden="true">' if icon_href else ""
    )
    content = f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="RaiPlayPodcast">
  <meta name="theme-color" content="#f5f7fb">
  {f'<link rel="apple-touch-icon" href="{icon_href}">' if icon_href else ''}
  {f'<link rel="icon" href="{icon_href}">' if icon_href else ''}
  <title>RaiPlayPodcast</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --ink: #111827;
      --muted: #697386;
      --line: rgba(15, 23, 42, 0.12);
      --panel: rgba(255, 255, 255, 0.82);
      --accent: #007aff;
      --accent-soft: rgba(0, 122, 255, 0.12);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(245, 247, 251, 0.92)),
        radial-gradient(circle at 20% 0%, rgba(0, 122, 255, 0.16), transparent 32%),
        var(--bg);
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
      padding: 0 2px 24px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 4rem);
      line-height: 0.95;
      letter-spacing: 0;
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .app-icon {{
      width: clamp(48px, 8vw, 72px);
      height: clamp(48px, 8vw, 72px);
      border-radius: 18px;
      box-shadow: 0 14px 30px rgba(220, 38, 38, 0.22);
    }}
    .summary {{
      margin: 0;
      color: var(--muted);
      font-size: 0.98rem;
      text-align: right;
    }}
    .program-list {{
      display: grid;
      gap: 14px;
      margin-top: 20px;
    }}
    .program-row {{
      display: grid;
      grid-template-columns: 116px minmax(0, 1fr);
      gap: 18px;
      align-items: center;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: var(--panel);
      box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
      backdrop-filter: blur(18px);
    }}
    .cover {{
      display: block;
      width: 116px;
      aspect-ratio: 1;
      overflow: hidden;
      border-radius: 18px;
      background: linear-gradient(135deg, #e8eef8, #ffffff);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.65);
    }}
    .cover img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .cover-placeholder {{
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, #dbeafe, #f8fafc);
    }}
    .program-title {{
      color: var(--ink);
      font-size: 1.28rem;
      font-weight: 760;
      text-decoration: none;
    }}
    .program-title:hover, .feed:hover {{ color: var(--accent); }}
    .program-author {{
      margin: 4px 0 0;
      color: var(--muted);
      font-weight: 600;
    }}
    .program-description {{
      margin: 10px 0 0;
      color: #2f3a4c;
      line-height: 1.45;
    }}
    .program-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .program-meta span, .feed {{
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(241, 245, 249, 0.9);
      color: inherit;
      text-decoration: none;
    }}
    .feed {{
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 700;
    }}
    @media (max-width: 680px) {{
      main {{ width: min(100% - 20px, 1120px); padding: 24px 0; }}
      header {{ display: block; }}
      .summary {{ margin-top: 8px; text-align: left; }}
      .program-row {{ grid-template-columns: 82px minmax(0, 1fr); gap: 12px; border-radius: 18px; }}
      .cover {{ width: 82px; border-radius: 15px; }}
      .program-title {{ font-size: 1.08rem; }}
      .program-description {{ font-size: 0.94rem; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{title_icon}RaiPlayPodcast</h1>
      <p class="summary">{len(items)} programmi sincronizzati</p>
    </header>
    <section class="program-list" aria-label="Programmi">
{chr(10).join(rows)}
    </section>
  </main>
</body>
</html>
"""
    index_path = target_base / "index.html"
    index_path.write_text(content, encoding="utf-8")
    return index_path
