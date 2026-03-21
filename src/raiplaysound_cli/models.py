from __future__ import annotations

import dataclasses
import re


@dataclasses.dataclass(slots=True)
class Program:
    slug: str
    title: str
    station_name: str
    station_short: str
    years: str
    page_url: str
    description_excerpt: str
    grouping_count: int


@dataclasses.dataclass(slots=True)
class Station:
    short: str
    name: str
    page_url: str
    feed_url: str


@dataclasses.dataclass(slots=True)
class Episode:
    episode_id: str
    url: str
    label: str
    title: str = ""
    upload_date: str = "NA"
    season: str = "1"
    year: str = "NA"
    group_label: str = ""
    group_kind: str = ""

    @property
    def pretty_date(self) -> str:
        if re.fullmatch(r"\d{8}", self.upload_date):
            return f"{self.upload_date[:4]}-{self.upload_date[4:6]}-{self.upload_date[6:8]}"
        return "unknown-date"


@dataclasses.dataclass(slots=True)
class EpisodeMetadata:
    upload_date: str = "NA"
    season: str = "NA"
    title: str = "NA"
    search_text: str = ""


@dataclasses.dataclass(slots=True)
class SeasonSummary:
    counts: dict[str, int]
    year_min: dict[str, str]
    year_max: dict[str, str]
    show_year_min: str
    show_year_max: str
    has_seasons: bool
    latest_season: str


@dataclasses.dataclass(slots=True)
class GroupSource:
    key: str
    label: str
    url: str
    kind: str


@dataclasses.dataclass(slots=True)
class GroupSummary:
    key: str
    label: str
    url: str
    kind: str
    episodes: int
    year_min: str
    year_max: str
