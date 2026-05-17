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


_SVG_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240" viewBox="0 0 640 240" role="img" aria-label="Xinyu Geng status card">
  <style>
    .bg            {{ fill: #FAFAF7; }}
    .text-primary  {{ fill: #1A1A1A; font-family: Georgia, 'Times New Roman', serif; }}
    .text-muted    {{ fill: #6B6B6B; font-family: Georgia, 'Times New Roman', serif; }}
    .mono          {{ fill: #1A1A1A; font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace; }}
    .mono-muted    {{ fill: #6B6B6B; font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace; }}
    .accent        {{ fill: #2F4858; }}
    @media (prefers-color-scheme: dark) {{
      .bg           {{ fill: #0F1014; }}
      .text-primary {{ fill: #E8E8E2; }}
      .text-muted   {{ fill: #8A8A85; }}
      .mono         {{ fill: #E8E8E2; }}
      .mono-muted   {{ fill: #8A8A85; }}
      .accent       {{ fill: #8FA8B5; }}
    }}
  </style>

  <rect class="bg" width="640" height="240"/>

  <!-- Title block -->
  <text x="320" y="48" text-anchor="middle" class="text-primary" font-size="28" font-style="italic">Xinyu Geng</text>
  <text x="320" y="72" text-anchor="middle" class="text-muted"   font-size="13">PhD · AI Security · AGH Krakow</text>

  <!-- Divider: ◆ ── ◇ ── ◆  (center ◇ breathes) -->
  <text x="320" y="98" text-anchor="middle" font-size="14" class="text-muted" letter-spacing="3">
    <tspan class="accent">◆</tspan>
    <tspan>──</tspan>
    <tspan class="accent" opacity="0.3">◇<animate attributeName="opacity" values="0.3;1;0.3" dur="3s" repeatCount="indefinite"/></tspan>
    <tspan>──</tspan>
    <tspan class="accent">◆</tspan>
  </text>

  <!-- Data rows -->
  <text x="100" y="134" class="mono-muted" font-size="13">⤷ now</text>
  <text x="195" y="134" class="mono"       font-size="13">{now}</text>

  <text x="100" y="160" class="mono-muted" font-size="13">⤷ reading</text>
  <text x="195" y="160" class="mono"       font-size="13">{reading}</text>

  <text x="100" y="186" class="mono-muted" font-size="13">⤷ warsaw</text>
  <text x="195" y="186" class="mono"       font-size="13">{warsaw}</text>

  <text x="100" y="212" class="mono-muted" font-size="13">⤷ github</text>
  <text x="195" y="212" class="mono"       font-size="13">{github}</text>

  <!-- Live indicator (bottom right) -->
  <text x="590" y="228" class="accent"     font-size="12" font-weight="bold">·<animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite"/></text>
  <text x="600" y="228" class="mono-muted" font-size="10">live</text>
</svg>
"""


def _truncate(text: str, max_chars: int = 48) -> str:
    """Trim text to fit inside the card without overflowing."""
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


def render_svg(
    status: dict,
    weather: Optional[tuple[float, str]],
    gh: Optional[GithubStats],
) -> str:
    """Return the complete SVG string."""
    # Warsaw value: "14:23 CET · ☁ 12°C"  (weather optional)
    warsaw = format_warsaw_time()
    if weather is not None:
        temp, glyph = weather
        warsaw = f"{warsaw} · {glyph} {round(temp)}°C"

    # GitHub value: "12d streak · last commit 2h ago" or "(offline)"
    if gh is None:
        github_value = "(offline)"
    elif gh.streak_days == 0:
        github_value = f"last commit {gh.last_commit_relative}"
    else:
        github_value = f"{gh.streak_days}d streak · last commit {gh.last_commit_relative}"

    return _SVG_TEMPLATE.format(
        now=_truncate(status["now"]),
        reading=_truncate(status["reading"]),
        warsaw=warsaw,
        github=github_value,
    )
