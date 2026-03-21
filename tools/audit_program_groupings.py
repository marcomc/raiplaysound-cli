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

from raiplaysound_cli import episodes as episodes_module
from raiplaysound_cli.episodes import (
    discover_group_listing_sources,
    discover_groups_from_program_payload,
)

USER_AGENT = "raiplaysound-cli-audit/1.0"
OUTPUT_DIR = Path("docs/audits")


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


episodes_module.http_get = http_get


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


def group_to_dict(slug: str, label: str, url: str, key: str, kind: str) -> dict[str, Any]:
    parsed = parse_program_filter_weblink(url.removeprefix("https://www.raiplaysound.it"))
    section = ""
    tail = ""
    if parsed is not None:
        _program_slug, section, tail = parsed
    return {
        "label": label,
        "weblink": url.removeprefix("https://www.raiplaysound.it"),
        "path": key,
        "section": section,
        "tail": tail,
        "key": key,
        "kind": kind,
        "active": url == f"https://www.raiplaysound.it/programmi/{slug}",
        "content_number": None,
    }


def derive_mode(groups: list[dict[str, Any]]) -> str:
    kinds = sorted({str(group["kind"]) for group in groups})
    if not groups:
        return "flat"
    if kinds and all(kind == "season" for kind in kinds):
        return "seasonal"
    if len(kinds) == 1:
        return kinds[0]
    return "mixed"

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
            "effective_group_count": 0,
            "grouped": False,
            "multi_group": False,
            "mode": "unreachable",
            "raw_sections": [],
            "raw_kinds": [],
            "raw_groups": [],
            "effective_sections": [],
            "effective_kinds": [],
            "effective_groups": [],
            "detected_by_current": False,
            "current_group_count": -1,
            "current_group_kinds": [],
            "missed_by_current": False,
            "fetch_error": "program-json-unavailable",
        }
    podcast_info = payload.get("podcast_info") if isinstance(payload.get("podcast_info"), dict) else {}
    title = str(payload.get("title") or podcast_info.get("title") or slug)
    channel = payload.get("channel") if isinstance(payload.get("channel"), dict) else {}
    if not channel and isinstance(podcast_info.get("channel"), dict):
        channel = podcast_info["channel"]
    station = str(channel.get("category_path") or "")
    filters = payload.get("filters") if isinstance(payload.get("filters"), list) else []
    tab_menu = payload.get("tab_menu") if isinstance(payload.get("tab_menu"), list) else []

    source_surfaces: list[str] = []
    if filters:
        source_surfaces.append("filters")
    if tab_menu:
        source_surfaces.append("tab_menu")

    payload_groups = discover_groups_from_program_payload(slug, payload)
    raw_groups = [
        group_to_dict(slug, group.label, group.url, group.key, group.kind) for group in payload_groups
    ]
    raw_sections = sorted({str(group["section"]) for group in raw_groups if group["section"]})
    raw_kinds = sorted({str(group["kind"]) for group in raw_groups})

    if payload_groups:
        try:
            _program_url, live_groups = discover_group_listing_sources(slug)
            effective_groups = [
                group_to_dict(slug, group.label, group.url, group.key, group.kind)
                for group in live_groups
            ]
            fetch_error = ""
        except Exception as exc:
            effective_groups = list(raw_groups)
            fetch_error = f"live-discovery-failed: {type(exc).__name__}: {exc}"
    else:
        effective_groups = list(raw_groups)
        fetch_error = ""

    effective_sections = sorted(
        {str(group["section"]) for group in effective_groups if group["section"]}
    )
    effective_kinds = sorted({str(group["kind"]) for group in effective_groups})

    grouped = bool(payload_groups)
    multi_group = len(payload_groups) > 1
    mode = derive_mode(raw_groups)

    return {
        "slug": slug,
        "title": title,
        "station": station,
        "program_url": f"https://www.raiplaysound.it/programmi/{slug}",
        "raw_group_count": len(raw_groups),
        "effective_group_count": len(effective_groups),
        "grouped": grouped,
        "multi_group": multi_group,
        "source_surfaces": source_surfaces,
        "mode": mode,
        "raw_sections": raw_sections,
        "raw_kinds": raw_kinds,
        "raw_groups": raw_groups,
        "effective_mode": derive_mode(effective_groups),
        "effective_sections": effective_sections,
        "effective_kinds": effective_kinds,
        "effective_groups": effective_groups,
        "detected_by_current": bool(effective_groups),
        "current_group_count": len(effective_groups),
        "current_group_kinds": effective_kinds,
        "missed_by_current": bool(raw_groups and not effective_groups),
        "fetch_error": fetch_error,
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
                "source_surfaces",
                "mode",
                "raw_group_count",
                "effective_group_count",
                "raw_sections",
                "effective_sections",
                "raw_kinds",
                "effective_kinds",
                "detected_by_current",
                "current_group_count",
                "current_group_kinds",
                "missed_by_current",
                "program_url",
                "sample_labels",
                "effective_sample_labels",
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
                    "|".join(item["source_surfaces"]),
                    item["mode"],
                    item["raw_group_count"],
                    item["effective_group_count"],
                    "|".join(item["raw_sections"]),
                    "|".join(item["effective_sections"]),
                    "|".join(item["raw_kinds"]),
                    "|".join(item["effective_kinds"]),
                    item["detected_by_current"],
                    item["current_group_count"],
                    "|".join(item["current_group_kinds"]),
                    item["missed_by_current"],
                    item["program_url"],
                    " | ".join(group["label"] for group in item["raw_groups"][:5]),
                    " | ".join(group["label"] for group in item["effective_groups"][:5]),
                    item.get("fetch_error", ""),
                ]
            )

    mode_counter: Counter[str] = Counter()
    section_counter: Counter[str] = Counter()
    surface_counter: Counter[str] = Counter()
    tab_menu_only_examples: list[dict[str, Any]] = []

    for item in results:
        mode_counter[item["mode"]] += 1
        for surface in item["source_surfaces"]:
            surface_counter[surface] += 1
        for section in item["raw_sections"]:
            section_counter[section] += 1
        if item["grouped"] and item["source_surfaces"] == ["tab_menu"]:
            tab_menu_only_examples.append(
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
        "effective_grouped_count": sum(1 for item in results if item["effective_groups"]),
        "multi_group_count": sum(1 for item in results if item["multi_group"]),
        "unreachable_count": sum(1 for item in results if item.get("fetch_error")),
        "effective_extra_root_groupings_count": sum(
            1
            for item in results
            if item["effective_group_count"] > item["raw_group_count"]
        ),
        "filters_surface_count": sum(1 for item in results if "filters" in item["source_surfaces"]),
        "tab_menu_surface_count": sum(1 for item in results if "tab_menu" in item["source_surfaces"]),
        "grouped_filters_count": sum(
            1 for item in results if item["grouped"] and "filters" in item["source_surfaces"]
        ),
        "grouped_tab_menu_count": sum(
            1 for item in results if item["grouped"] and "tab_menu" in item["source_surfaces"]
        ),
        "grouped_tab_menu_only_count": sum(
            1 for item in results if item["grouped"] and item["source_surfaces"] == ["tab_menu"]
        ),
        "grouped_filters_and_tab_menu_count": sum(
            1
            for item in results
            if item["grouped"] and set(item["source_surfaces"]) == {"filters", "tab_menu"}
        ),
        "mode_counter": dict(mode_counter.most_common()),
        "surface_counter": dict(surface_counter.most_common()),
        "top_sections": section_counter.most_common(20),
        "examples_tab_menu_only": tab_menu_only_examples[:25],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"WROTE {json_path}")
    print(f"WROTE {csv_path}")
    print(f"WROTE {summary_path}")


def main() -> int:
    slugs = catalog_slugs()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(analyze_program, slug): slug for slug in slugs}
        total = len(future_map)
        completed = 0
        for future in concurrent.futures.as_completed(future_map):
            item = future.result()
            results.append(item)
            completed += 1
            if completed % 100 == 0 or completed == total:
                print(f"progress {completed}/{total}", flush=True)
    results.sort(key=lambda item: str(item["slug"]))
    write_outputs(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
