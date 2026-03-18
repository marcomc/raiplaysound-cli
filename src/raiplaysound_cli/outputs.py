from __future__ import annotations

import email.utils
import re
import time
import urllib.parse
from pathlib import Path

from .catalog import fetch_program_metadata
from .episodes import load_metadata_cache

DATE_IN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def fetch_show_title(slug: str) -> str:
    program = fetch_program_metadata(slug)
    return program.title if program else slug


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


def generate_rss_feed(
    target_dir: Path,
    slug: str,
    program_url: str,
    metadata_cache_file: Path,
    base_url: str,
) -> Path:
    cache_by_date: dict[str, list[tuple[str, str]]] = {}
    for episode_id, (upload, _season, title) in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", upload):
            cache_by_date.setdefault(f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}", []).append(
                (title, episode_id)
            )
    show_title = fetch_show_title(slug)
    items = []
    for file_path in sorted(target_dir.iterdir(), reverse=True):
        if not file_path.is_file():
            continue
        match = DATE_IN_NAME_RE.search(file_path.name)
        if not match:
            continue
        file_date = match.group(1)
        dated_entries = cache_by_date.get(file_date, [])
        if len(dated_entries) == 1:
            title, guid = dated_entries[0]
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
        f"    <description>{xml_escape(show_title)}</description>",
        "    <language>it</language>",
        f"    <itunes:title>{xml_escape(show_title)}</itunes:title>",
        "    <itunes:author>RAI Play Sound</itunes:author>",
        "    <itunes:explicit>false</itunes:explicit>",
    ]
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
    for _episode_id, (upload, _season, title) in load_metadata_cache(metadata_cache_file).items():
        if re.fullmatch(r"\d{8}", upload):
            cache_by_date.setdefault(f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}", []).append(title)
    entries: list[tuple[str, Path]] = []
    for file_path in target_dir.iterdir():
        if file_path.is_file():
            match = DATE_IN_NAME_RE.search(file_path.name)
            if match:
                entries.append((match.group(1), file_path))
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
