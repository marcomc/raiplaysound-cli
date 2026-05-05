from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from .episodes import load_metadata_cache
from .outputs import AUDIO_SUFFIXES, DATE_IN_NAME_RE, _filename_title, _metadata_date, _title_key

TITLE_DATE_RE = re.compile(r"\b(\d{2})[/\u29f8](\d{2})[/\u29f8](\d{4})\b")


@dataclasses.dataclass(slots=True)
class FilenameRepair:
    source: Path
    target: Path
    title: str
    date: str


@dataclasses.dataclass(slots=True)
class FilenameRepairPlan:
    repairs: list[FilenameRepair]
    ambiguous: list[Path]
    conflicts: list[tuple[Path, Path]]
    unmatched: list[Path]


def plan_filename_repairs(show_dir: Path, metadata_cache_file: Path) -> FilenameRepairPlan:
    title_to_entry: dict[str, tuple[str, str] | None] = {}
    for _episode_id, metadata in load_metadata_cache(metadata_cache_file).items():
        metadata_date = _metadata_date(metadata.upload_date)
        if metadata_date is None:
            continue
        key = _title_key(metadata.title)
        if key in title_to_entry:
            title_to_entry[key] = None
        else:
            title_to_entry[key] = (metadata.title, metadata_date)

    repairs: list[FilenameRepair] = []
    ambiguous: list[Path] = []
    conflicts: list[tuple[Path, Path]] = []
    unmatched: list[Path] = []

    for source in _iter_audio_files(show_dir):
        match = DATE_IN_NAME_RE.search(source.name)
        if match is None:
            unmatched.append(source)
            continue
        filename_title = _filename_title(source)
        entry = title_to_entry.get(_title_key(filename_title))
        if entry is None:
            if _title_key(_filename_title(source)) in title_to_entry:
                ambiguous.append(source)
                continue
            title_date = _date_from_title(filename_title)
            if title_date is None:
                unmatched.append(source)
                continue
            title = filename_title
            metadata_date = title_date
        else:
            title, metadata_date = entry
        if match.group(1) == metadata_date:
            continue
        target_name = DATE_IN_NAME_RE.sub(metadata_date, source.name, count=1)
        target = source.with_name(target_name)
        if target.exists():
            conflicts.append((source, target))
            continue
        repairs.append(
            FilenameRepair(
                source=source,
                target=target,
                title=title,
                date=metadata_date,
            )
        )

    return FilenameRepairPlan(
        repairs=repairs,
        ambiguous=ambiguous,
        conflicts=conflicts,
        unmatched=unmatched,
    )


def apply_filename_repairs(repairs: list[FilenameRepair]) -> None:
    for repair in repairs:
        repair.source.rename(repair.target)


def _date_from_title(title: str) -> str | None:
    match = TITLE_DATE_RE.search(title)
    if match is None:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _iter_audio_files(show_dir: Path) -> list[Path]:
    try:
        entries = list(show_dir.iterdir())
    except OSError:
        return []
    return sorted(
        (
            path
            for path in entries
            if path.is_file()
            and path.suffix.lower() in AUDIO_SUFFIXES
            and not re.match(r"^\.", path.name)
        ),
        key=lambda path: path.name.casefold(),
    )
