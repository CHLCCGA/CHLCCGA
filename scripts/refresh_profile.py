"""Regenerate profile status card SVG + update the card link in README.

Reads data/status.yaml as the single source of manual data, fetches Warsaw
weather, the last GitHub push and the top alphaXiv paper from public APIs, then writes:
  - assets/status-card.svg
  - README.md  (card link between <!-- card-href:start --> markers)

Run with --dry-run to print outputs to stdout without writing files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, date
from html import unescape
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape
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


def fetch_last_push() -> Optional[date]:
    """Warsaw-local date of the user's most recent public push, or None on failure / no pushes."""
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
        return None
    last_push_utc = datetime.fromisoformat(pushes[0]["created_at"].replace("Z", "+00:00"))
    return last_push_utc.astimezone(WARSAW_TZ).date()


@dataclass
class TrendingPaper:
    display: str       # title or "title · first_author et al."
    arxiv_id: str      # e.g. "2605.15188"


def fetch_alphaxiv_trending() -> Optional[TrendingPaper]:
    """Scrape alphaxiv.org homepage for the top trending paper.

    Returns TrendingPaper(display, arxiv_id), or None on failure.
    The homepage is SSR'd Next.js — paper data is in the rendered HTML.
    """
    try:
        req = urllib.request.Request(
            "https://www.alphaxiv.org/",
            headers={"User-Agent": "refresh_profile/1.0", "Accept-Encoding": "gzip"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            html = raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"warning: alphaxiv fetch failed: {e}", file=sys.stderr)
        return None

    href_m = re.search(r'href="/?abs/(\d{4}\.\d{4,5})"', html)
    if not href_m:
        return None
    arxiv_id = href_m.group(1)

    window = html[href_m.end():href_m.end() + 4000]
    title_m = re.search(r'<h2 class="[^"]*font-title[^"]*"[^>]*>([^<]+)</h2>', window)
    if not title_m:
        print("warning: alphaxiv layout changed, no title found", file=sys.stderr)
        return None
    title = unescape(title_m.group(1)).strip()

    display = title
    # First author is either a plain <button> or a linked profile <a rel="author">…<span>Name</span>
    author_m = re.search(
        r'<button[^>]*type="button"[^>]*>([^<]+)</button>|<a rel="author"[^>]*>.*?<span[^>]*>([^<]+)</span>',
        window[title_m.end():],
    )
    if author_m:
        combined = f"{title} · {unescape(author_m.group(1) or author_m.group(2)).strip()} et al."
        # If combined overflows the two value lines, drop the author tail rather than the title
        if len(combined) <= 2 * _VALUE_CHARS:
            display = combined

    return TrendingPaper(display=display, arxiv_id=arxiv_id)


# Card geometry. 480 wide so the text stays readable when GitHub mobile scales the
# image down; the background is transparent so it sits on GitHub's own light/dark page.
_CARD_W      = 480
_LABEL_X     = 64
_VALUE_X     = 144
_ROW_TOP     = 112   # baseline of the first data row
_ROW_STEP    = 24
_VALUE_CHARS = 40    # ~312px of 13px monospace between _VALUE_X and the right padding

_SVG_HEAD = """\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Xinyu Geng status card">
  <style>
    .text-primary  {{ fill: #24292F; font-family: Georgia, 'Times New Roman', serif; }}
    .text-muted    {{ fill: #57606A; font-family: Georgia, 'Times New Roman', serif; }}
    .mono          {{ fill: #24292F; font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace; }}
    .mono-muted    {{ fill: #57606A; font-family: 'SF Mono', Menlo, Consolas, 'Courier New', monospace; }}
    @media (prefers-color-scheme: dark) {{
      .text-primary {{ fill: #E6EDF3; }}
      .text-muted   {{ fill: #9DA7B3; }}
      .mono         {{ fill: #E6EDF3; }}
      .mono-muted   {{ fill: #9DA7B3; }}
    }}
  </style>

  <text x="{cx}" y="46" text-anchor="middle" class="text-primary" font-size="28" font-style="italic">Xinyu Geng</text>
  <text x="{cx}" y="70" text-anchor="middle" class="text-muted"   font-size="14">PhD · AI Security · AGH Krakow</text>
"""


def _wrap(text: str, width: int = _VALUE_CHARS, max_lines: int = 2) -> list[str]:
    """Greedy word wrap into at most `max_lines` lines; the last line gets an ellipsis if cut."""
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return [line if len(line) <= width else line[: width - 1] + "…" for line in lines]


def render_svg(
    weather: Optional[tuple[float, str]],
    last_push: Optional[date],
    reading: Optional[str],
) -> str:
    """Return the complete SVG string. Rows whose data could not be fetched are left out."""
    rows: list[tuple[str, list[str]]] = []
    if reading:
        rows.append(("reading", _wrap(reading)))
    if weather is not None:
        temp, glyph = weather
        rows.append(("warsaw", [f"{glyph} {round(temp)}°C"]))
    if last_push is not None:
        rows.append(("github", [f"last push {last_push.strftime('%b')} {last_push.day}"]))

    body = []
    y = _ROW_TOP
    for label, lines in rows:
        body.append(f'  <text x="{_LABEL_X}" y="{y}" class="mono-muted" font-size="13">{label}</text>')
        for line in lines:
            body.append(f'  <text x="{_VALUE_X}" y="{y}" class="mono" font-size="13">{escape(line)}</text>')
            y += _ROW_STEP
    height = (y - _ROW_STEP + 26) if rows else 90

    head = _SVG_HEAD.format(w=_CARD_W, h=height, cx=_CARD_W // 2)
    return head + "\n".join(body) + "\n</svg>\n"


_CARD_HREF_START = "<!-- card-href:start -->"
_CARD_HREF_END   = "<!-- card-href:end -->"
_CARD_HREF_RE    = re.compile(
    rf"{re.escape(_CARD_HREF_START)}.*?{re.escape(_CARD_HREF_END)}",
    re.DOTALL,
)


def _format_card_href(card_url: str) -> str:
    """The clickable image block: <a href><img></a> with markers around it."""
    return (
        f'{_CARD_HREF_START}'
        f'<a href="{card_url}"><img src="assets/status-card.svg" alt="Xinyu Geng — status card" /></a>'
        f'{_CARD_HREF_END}'
    )


def update_card_href(readme: str, card_url: str) -> str:
    """Replace the wrapped <a><img></a> block so the card links to the current paper."""
    if not _CARD_HREF_RE.search(readme):
        raise RuntimeError(
            f"card-href markers not found in README.md; expected '{_CARD_HREF_START}' "
            f"and '{_CARD_HREF_END}'"
        )
    return _CARD_HREF_RE.sub(_format_card_href(card_url), readme)


def main(dry_run: bool = False) -> None:
    status = load_status()
    weather = fetch_weather()
    last_push = fetch_last_push()

    # Resolve reading: 'auto' triggers alphaxiv fetch (string + arxiv id); else use literal
    yaml_reading = (status.get("reading") or "").strip()
    trending: Optional[TrendingPaper] = None
    if yaml_reading.lower() == "auto":
        trending = fetch_alphaxiv_trending()
        reading_str = trending.display if trending else None
    else:
        reading_str = yaml_reading

    card_url = (
        f"https://www.alphaxiv.org/abs/{trending.arxiv_id}"
        if trending else "https://www.alphaxiv.org/"
    )

    svg = render_svg(weather, last_push, reading_str)
    new_readme = update_card_href(README_PATH.read_text(encoding="utf-8"), card_url)

    if dry_run:
        print("=== status-card.svg ===")
        print(svg)
        print()
        print("=== README.md (after card-href injection) ===")
        print(new_readme)
        return

    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")
    README_PATH.write_text(new_readme, encoding="utf-8")
    print(f"wrote {SVG_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {README_PATH.relative_to(REPO_ROOT)}")
    if trending:
        print(f"card -> https://www.alphaxiv.org/abs/{trending.arxiv_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print outputs to stdout without writing files")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
