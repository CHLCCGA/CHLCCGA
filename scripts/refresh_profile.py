"""Regenerate profile status card SVG + inject papers block into README.

Reads data/status.yaml as the single source of manual data, fetches Warsaw
weather and GitHub commit stats from public APIs, then writes:
  - assets/status-card.svg
  - README.md  (papers block between <!-- papers:start --> markers)

Run with --dry-run to print outputs to stdout without writing files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_YAML = REPO_ROOT / "data" / "status.yaml"
SVG_PATH    = REPO_ROOT / "assets" / "status-card.svg"
README_PATH = REPO_ROOT / "README.md"

GITHUB_USER = "CHLCCGA"
WARSAW_TZ   = ZoneInfo("Europe/Warsaw")


def load_status() -> dict:
    """Load the hand-maintained status YAML."""
    with STATUS_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_warsaw_time() -> str:
    """Return current Warsaw time as 'HH:MM CET' or 'HH:MM CEST'."""
    now = datetime.now(WARSAW_TZ)
    return now.strftime("%H:%M %Z")


# Open-Meteo WMO weather codes → single glyph.
# Source: https://open-meteo.com/en/docs (under "weather_code")
_WEATHER_GLYPHS = {
    0: "☀",                                                       # clear sky
    1: "⛅", 2: "⛅", 3: "⛅",                              # partly cloudy
    45: "☁", 48: "☁",                                         # fog
    51: "☂", 53: "☂", 55: "☂",                           # drizzle
    56: "☂", 57: "☂",                                         # freezing drizzle
    61: "☂", 63: "☂", 65: "☂",                           # rain
    66: "☂", 67: "☂",                                         # freezing rain
    71: "❄", 73: "❄", 75: "❄", 77: "❄",             # snow
    80: "☂", 81: "☂", 82: "☂",                           # rain showers
    85: "❄", 86: "❄",                                         # snow showers
    95: "☂", 96: "☂", 99: "☂",                           # thunderstorm
}


def fetch_weather() -> Optional[tuple[float, str]]:
    """Return (temperature_celsius, glyph) for Warsaw, or None on failure."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=52.23&longitude=21.01&current=temperature_2m,weather_code"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read())
    except Exception as e:
        print(f"warning: weather fetch failed: {e}", file=sys.stderr)
        return None

    current = payload.get("current", {})
    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    if temp is None or code is None:
        return None
    return (temp, _WEATHER_GLYPHS.get(code, "·"))


@dataclass
class GithubStats:
    streak_days: int
    last_commit_relative: str   # e.g. "2h ago", "3d ago"


def _relative_time(then_utc: datetime) -> str:
    """Format a UTC datetime as relative-from-now."""
    delta = datetime.now(timezone.utc) - then_utc
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m ago"


def _streak_from_dates(push_dates_utc: list[date]) -> int:
    """Count consecutive days backwards from the most recent push date."""
    if not push_dates_utc:
        return 0
    sorted_dates = sorted(set(push_dates_utc), reverse=True)
    streak = 1
    prev = sorted_dates[0]
    for d in sorted_dates[1:]:
        if (prev - d).days == 1:
            streak += 1
            prev = d
        else:
            break
    return streak


def fetch_github_stats() -> Optional[GithubStats]:
    """Pull the last 100 public events for the user and compute streak + last push."""
    url = f"https://api.github.com/users/{GITHUB_USER}/events/public?per_page=100"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "refresh_profile/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read())
    except Exception as e:
        print(f"warning: github fetch failed: {e}", file=sys.stderr)
        return None

    pushes = [e for e in events if e.get("type") == "PushEvent"]
    if not pushes:
        return GithubStats(streak_days=0, last_commit_relative="no commits")

    last_push_utc = datetime.fromisoformat(pushes[0]["created_at"].replace("Z", "+00:00"))
    push_dates = [
        datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).date()
        for e in pushes
    ]
    return GithubStats(
        streak_days=_streak_from_dates(push_dates),
        last_commit_relative=_relative_time(last_push_utc),
    )
