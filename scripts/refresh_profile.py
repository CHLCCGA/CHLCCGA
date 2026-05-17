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
