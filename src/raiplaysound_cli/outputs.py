from __future__ import annotations

import email.utils
import html
import json
import re
import time
import urllib.parse
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


def _url_for_artifact(path: Path, slug: str, base_url: str) -> str:
    if base_url:
        return f"{base_url.rstrip('/')}/{slug}/{urllib.parse.quote(path.name)}"
    return urllib.parse.quote(path.name)


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


def prepare_program_assets(target_dir: Path, slug: str, program_url: str) -> ProgramDetails:
    details = fetch_program_details(slug) or fallback_program_details(slug, program_url)
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
        raw, _content_type = http_get_bytes(INDEX_ICON_URL, timeout=30.0)
    except Exception:
        return icon_path if icon_path.exists() else None
    icon_path.write_bytes(raw)
    return icon_path


def _local_audio_entries(target_dir: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for file_path in target_dir.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        match = DATE_IN_NAME_RE.search(file_path.name)
        if match:
            entries.append((match.group(1), file_path))
    return entries


def generate_rss_feed(
    target_dir: Path,
    slug: str,
    program_url: str,
    metadata_cache_file: Path,
    base_url: str,
    details: ProgramDetails | None = None,
) -> Path:
    cache_by_date: dict[str, list[tuple[str, str]]] = {}
    for episode_id, metadata in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", metadata.upload_date):
            cache_by_date.setdefault(
                (
                    f"{metadata.upload_date[:4]}-"
                    f"{metadata.upload_date[4:6]}-"
                    f"{metadata.upload_date[6:8]}"
                ),
                [],
            ).append((metadata.title, episode_id))
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
    items = []
    for file_date, file_path in sorted(_local_audio_entries(target_dir), reverse=True):
        dated_entries = cache_by_date.get(file_date, [])
        if len(dated_entries) == 1:
            title, guid = dated_entries[0]
        else:
            title = re.sub(r"^.*\d{4}-\d{2}-\d{2}\s+-\s+", "", file_path.stem)
            guid = file_path.stem
        enclosure = _url_for_artifact(file_path, slug, base_url)
        items.append(
            {
                "title": title,
                "guid": guid,
                "pub_date": email.utils.formatdate(
                    time.mktime(time.strptime(file_date, "%Y-%m-%d")),
                    usegmt=True,
                ),
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
    for item in items:
        enclosure_tag = (
            f"      <enclosure url=\"{xml_escape(item['enclosure'])}\" "
            f"length=\"{item['size']}\" type=\"{xml_escape(item['mime'])}\"/>"
        )
        lines.extend(
            [
                "    <item>",
                f"      <title>{xml_escape(item['title'])}</title>",
                f"      <link>{xml_escape(program_url)}</link>",
                f"      <guid isPermaLink=\"false\">{xml_escape(item['guid'])}</guid>",
                f"      <pubDate>{item['pub_date']}</pubDate>",
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
    for _episode_id, metadata in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", metadata.upload_date):
            cache_by_date.setdefault(
                (
                    f"{metadata.upload_date[:4]}-"
                    f"{metadata.upload_date[4:6]}-"
                    f"{metadata.upload_date[6:8]}"
                ),
                [],
            ).append(metadata.title)
    entries: list[tuple[str, Path]] = []
    entries.extend(_local_audio_entries(target_dir))
    entries.sort(key=lambda item: item[0])
    lines = ["#EXTM3U"]
    for file_date, file_path in entries:
        dated_titles = cache_by_date.get(file_date, [])
        if len(dated_titles) == 1:
            title = dated_titles[0]
        else:
            title = re.sub(
                r"^.*\d{4}-\d{2}-\d{2}\s+-\s+",
                "",
                file_path.stem,
            )
        lines.append(f"#EXTINF:-1,{title}")
        lines.append(file_path.name)
    playlist_path = target_dir / "playlist.m3u"
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist_path


def _program_index_item(show_dir: Path, base_url: str) -> dict[str, str | int]:
    slug = show_dir.name
    details = ensure_program_assets(show_dir, slug)
    audio_entries = _local_audio_entries(show_dir)
    latest_date = max((date for date, _path in audio_entries), default="")
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
        "feed_href": feed_href if feed_path.exists() else "",
        "artwork_href": artwork_href,
        "episode_count": len(audio_entries),
        "latest_date": latest_date,
    }


def generate_program_index(target_base: Path, base_url: str = "") -> Path:
    target_base.mkdir(parents=True, exist_ok=True)
    icon_path = download_index_icon(target_base)
    icon_href = urllib.parse.quote(icon_path.name) if icon_path is not None else ""
    items = [
        _program_index_item(show_dir, base_url)
        for show_dir in sorted(target_base.iterdir(), key=lambda item: item.name.casefold())
        if show_dir.is_dir() and not show_dir.name.startswith(".")
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
    content = f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="RaiPlaySound">
  <meta name="theme-color" content="#f5f7fb">
  {f'<link rel="apple-touch-icon" href="{icon_href}">' if icon_href else ''}
  {f'<link rel="icon" href="{icon_href}">' if icon_href else ''}
  <title>RaiPlaySound Podcast</title>
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
      <h1>Podcast</h1>
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
