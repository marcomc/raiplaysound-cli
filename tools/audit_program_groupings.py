from __future__ import annotations

import concurrent.futures
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from raiplaysound_cli.episodes import discover_group_listing_sources

USER_AGENT = "raiplaysound-cli-audit/1.0"
OUTPUT_DIR = Path("docs/audits")
SEASON_RE = re.compile(r"(?:stagione\s+(\d+)|(\d+)\s*stagione)", re.IGNORECASE)
YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def http_get(url: str, *, timeout: int = 30) -> str:
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            str(timeout),
            "--user-agent",
            USER_AGENT,
            "--header",
            "Accept: */*",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def normalize_label(value: str) -> str:
    return " ".join(value.split())


def normalize_token(value: str) -> str:
    chunks: list[str] = []
    last_dash = False
    for char in value.lower():
        if char.isalnum():
            chunks.append(char)
            last_dash = False
            continue
        if not last_dash:
            chunks.append("-")
            last_dash = True
    return "".join(chunks).strip("-")


def parse_program_filter_weblink(weblink: str) -> tuple[str, str, str] | None:
    parts = weblink.strip("/").split("/")
    if len(parts) < 4 or parts[0] != "programmi":
        return None
    return parts[1], parts[2], "/".join(parts[3:])


def season_key(label: str, tail: str) -> str | None:
    match = SEASON_RE.search(label)
    if match:
        return match.group(1) or match.group(2)
    if tail.startswith("stagione-"):
        suffix = tail.removeprefix("stagione-")
        if suffix.isdigit():
            return suffix
    return None


def generalized_kind(section: str, label: str, path: str, tail: str) -> str:
    joined = " ".join([section, label, path, tail]).lower()
    if season_key(label, tail) is not None:
        return "season"
    if "special" in joined:
        return "special"
    if "replic" in joined:
        return "replica"
    if (
        YEAR_RE.fullmatch(label.strip())
        or YEAR_RE.fullmatch(path.strip())
        or YEAR_RE.fullmatch(tail.strip())
    ):
        return "year"
    if section in {"cicli", "ciclo", "cicli-e-podcast"}:
        return "cycle"
    if section in {"puntate-e-podcast", "podcast", "serie", "seriali"}:
        return "series"
    if section in {"collezioni", "collection", "collections"}:
        return "collection"
    if section in {"episodi", "puntate"} and tail not in {"episodi", "puntate"}:
        return "bucket"
    return "other"


def catalog_slugs() -> list[str]:
    root = ET.fromstring(http_get("https://www.raiplaysound.it/sitemap.archivio.programmi.xml"))
    slugs: set[str] = set()
    for element in root.iter():
        if not element.tag.endswith("loc"):
            continue
        text = (element.text or "").strip()
        marker = "sitemap.programmi."
        if marker not in text or not text.endswith(".xml"):
            continue
        slugs.add(text.split(marker, 1)[1][:-4])
    return sorted(slugs)


def fetch_program_payload(slug: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(http_get(f"https://www.raiplaysound.it/programmi/{slug}.json"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def analyze_program(slug: str) -> dict[str, Any]:
    payload = fetch_program_payload(slug)
    if payload is None:
        return {
            "slug": slug,
            "title": slug,
            "station": "",
            "program_url": f"https://www.raiplaysound.it/programmi/{slug}",
            "raw_group_count": 0,
            "grouped": False,
            "multi_group": False,
            "mode": "unreachable",
            "raw_sections": [],
            "raw_kinds": [],
            "raw_groups": [],
            "detected_by_current": False,
            "current_group_count": -1,
            "current_group_kinds": [],
            "missed_by_current": False,
            "fetch_error": "program-json-unavailable",
        }
    title = str(payload.get("title") or slug)
    channel = payload.get("channel") if isinstance(payload.get("channel"), dict) else {}
    station = str(channel.get("category_path") or "")
    filters = payload.get("filters") if isinstance(payload.get("filters"), list) else []

    raw_groups: list[dict[str, Any]] = []
    sections: set[str] = set()
    kinds: set[str] = set()

    for item in filters:
        if not isinstance(item, dict):
            continue
        label = normalize_label(str(item.get("label") or ""))
        weblink = str(item.get("weblink") or "").rstrip("/")
        path = str(item.get("path") or "")
        active = bool(item.get("active"))
        content_number: int | None = None
        content_size = item.get("content_size")
        if isinstance(content_size, dict) and isinstance(content_size.get("number"), int):
            content_number = int(content_size["number"])

        parsed = parse_program_filter_weblink(weblink)
        section = ""
        tail = ""
        if parsed is not None:
            _program_slug, section, tail = parsed
        kind = generalized_kind(section, label, path, tail) if parsed is not None else "other"
        key = season_key(label, tail) or (path or tail or normalize_token(label))

        raw_groups.append(
            {
                "label": label,
                "weblink": weblink,
                "path": path,
                "section": section,
                "tail": tail,
                "key": key,
                "kind": kind,
                "active": active,
                "content_number": content_number,
            }
        )
        if section:
            sections.add(section)
        kinds.add(kind)

    try:
        _program_url, current_groups = discover_group_listing_sources(slug)
        detected_by_current = bool(current_groups)
        current_group_count = len(current_groups)
        current_group_kinds = sorted({group.kind for group in current_groups})
    except Exception as exc:  # pragma: no cover - live audit helper
        detected_by_current = False
        current_group_count = -1
        current_group_kinds = [f"error:{type(exc).__name__}"]

    grouped = any(group["weblink"] and group["key"] for group in raw_groups)
    multi_group = sum(1 for group in raw_groups if group["weblink"] and group["key"]) > 1
    missed_by_current = grouped and not detected_by_current

    sorted_kinds = sorted(kinds)
    if not grouped:
        mode = "flat"
    elif sorted_kinds and all(kind == "season" for kind in sorted_kinds):
        mode = "seasonal"
    elif len(sorted_kinds) == 1:
        mode = sorted_kinds[0]
    else:
        mode = "mixed"

    return {
        "slug": slug,
        "title": title,
        "station": station,
        "program_url": f"https://www.raiplaysound.it/programmi/{slug}",
        "raw_group_count": len(raw_groups),
        "grouped": grouped,
        "multi_group": multi_group,
        "mode": mode,
        "raw_sections": sorted(sections),
        "raw_kinds": sorted_kinds,
        "raw_groups": raw_groups,
        "detected_by_current": detected_by_current,
        "current_group_count": current_group_count,
        "current_group_kinds": current_group_kinds,
        "missed_by_current": missed_by_current,
        "fetch_error": "",
    }


def write_outputs(results: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "program-grouping-audit.json"
    csv_path = OUTPUT_DIR / "program-grouping-audit.csv"
    summary_path = OUTPUT_DIR / "program-grouping-summary.json"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "slug",
                "title",
                "station",
                "grouped",
                "multi_group",
                "mode",
                "raw_group_count",
                "raw_sections",
                "raw_kinds",
                "detected_by_current",
                "current_group_count",
                "current_group_kinds",
                "missed_by_current",
                "program_url",
                "sample_labels",
                "fetch_error",
            ]
        )
        for item in results:
            writer.writerow(
                [
                    item["slug"],
                    item["title"],
                    item["station"],
                    item["grouped"],
                    item["multi_group"],
                    item["mode"],
                    item["raw_group_count"],
                    "|".join(item["raw_sections"]),
                    "|".join(item["raw_kinds"]),
                    item["detected_by_current"],
                    item["current_group_count"],
                    "|".join(item["current_group_kinds"]),
                    item["missed_by_current"],
                    item["program_url"],
                    " | ".join(group["label"] for group in item["raw_groups"][:5]),
                    item.get("fetch_error", ""),
                ]
            )

    mode_counter: Counter[str] = Counter()
    section_counter: Counter[str] = Counter()
    missed_section_counter: Counter[str] = Counter()
    missed_examples: list[dict[str, Any]] = []

    for item in results:
        mode_counter[item["mode"]] += 1
        for section in item["raw_sections"]:
            section_counter[section] += 1
        if item["missed_by_current"]:
            for section in item["raw_sections"]:
                missed_section_counter[section] += 1
            missed_examples.append(
                {
                    "slug": item["slug"],
                    "title": item["title"],
                    "sections": item["raw_sections"],
                    "kinds": item["raw_kinds"],
                    "sample_labels": [group["label"] for group in item["raw_groups"][:5]],
                }
            )

    summary = {
        "program_count": len(results),
        "grouped_count": sum(1 for item in results if item["grouped"]),
        "multi_group_count": sum(1 for item in results if item["multi_group"]),
        "missed_by_current_count": sum(1 for item in results if item["missed_by_current"]),
        "unreachable_count": sum(1 for item in results if item.get("fetch_error")),
        "mode_counter": dict(mode_counter.most_common()),
        "top_sections": section_counter.most_common(20),
        "top_missed_sections": missed_section_counter.most_common(20),
        "examples_missed": missed_examples[:25],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"WROTE {json_path}")
    print(f"WROTE {csv_path}")
    print(f"WROTE {summary_path}")


def main() -> int:
    slugs = catalog_slugs()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        for item in executor.map(analyze_program, slugs):
            results.append(item)
    results.sort(key=lambda item: str(item["slug"]))
    write_outputs(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
