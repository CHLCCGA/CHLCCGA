#!/usr/bin/env python3
"""Generate GitHub profile card SVG with dynamic AI news and GitHub trending."""

import urllib.request
import json
import datetime
import os
import html
import xml.etree.ElementTree as ET

# ── Helpers ───────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    return html.escape(str(text), quote=False)

def trunc(text: str, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"

def stars_fmt(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

# ── Fetch AI news (HuggingFace blog RSS) ─────────────────────────────────────
def fetch_ai_news():
    url = "https://huggingface.co/blog/feed.xml"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CHLCCGA-profile-card/1.0")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.parse(resp).getroot()
            items = root.findall(".//item")[:3]
            titles = [trunc(esc((i.findtext("title") or "").strip()), 32) for i in items]
            return titles if len(titles) == 3 else None
    except Exception as e:
        print(f"Warning: AI news fetch failed ({e}), using placeholders.")
        return None

AI_NEWS_FALLBACK = [
    "LLM robustness benchmarks drop",
    "New multimodal safety dataset",
    "Agentic attack surfaces paper",
]

# ── Fetch GitHub trending ─────────────────────────────────────────────────────
def fetch_trending():
    since = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    url = (
        "https://api.github.com/search/repositories"
        f"?q=created:>{since}&sort=stars&order=desc&per_page=3"
    )
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "CHLCCGA-profile-card/1.0")
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read()).get("items", [])[:3]
            return [(r["full_name"], r["stargazers_count"]) for r in items]
    except Exception as e:
        print(f"Warning: trending fetch failed ({e}), using placeholders.")
        return [
            ("anthropics/claude-code", 12300),
            ("huggingface/smollm3", 8700),
            ("openai/openai-agents", 6100),
        ]

# ── SVG generation ─────────────────────────────────────────────────────────────
def generate_svg(ai_news, trending) -> str:
    # Trending lines
    t = [f"★{stars_fmt(s)}  {trunc(esc(name), 25)}" for name, s in trending]
    while len(t) < 3:
        t.append("")

    # AI news lines
    n = ai_news if ai_news else AI_NEWS_FALLBACK
    while len(n) < 3:
        n.append("")

    # Palette
    BG     = "#0D0D0D"
    BORDER = "#DA7756"
    ACCENT = "#DA7756"
    TEXT   = "#E0E0E0"
    DIM    = "#6E6E6E"
    DOG    = "#C8855A"   # warm tan/brown dog body
    EAR    = "#9A6030"   # darker brown for ears + legs
    DEYE   = "#2D1000"   # very dark brown for eyes/nose

    # ── pixel dog (centered at x=230) ─────────────────────────────────────────
    # Body width=72, x=194..266; each pixel-unit ≈ 8px
    dog = f"""
  <!-- floppy ears (hang from sides of head) -->
  <rect x="182" y="66" width="14" height="32" fill="{EAR}"/>
  <rect x="264" y="66" width="14" height="32" fill="{EAR}"/>
  <!-- head block -->
  <rect x="194" y="62" width="72" height="38" fill="{DOG}"/>
  <!-- left eye -->
  <rect x="208" y="74" width="12" height="12" fill="{DEYE}"/>
  <rect x="210" y="75" width="4"  height="4"  fill="white" opacity="0.45"/>
  <!-- right eye -->
  <rect x="240" y="74" width="12" height="12" fill="{DEYE}"/>
  <rect x="242" y="75" width="4"  height="4"  fill="white" opacity="0.45"/>
  <!-- nose -->
  <rect x="225" y="89" width="10" height="8"  fill="{DEYE}"/>
  <!-- body -->
  <rect x="200" y="100" width="60" height="18" fill="{DOG}"/>
  <!-- tail (stub right side, angled up) -->
  <rect x="258" y="92" width="10" height="16" fill="{EAR}"/>
  <rect x="264" y="85" width="8"  height="10" fill="{EAR}"/>
  <!-- front legs -->
  <rect x="200" y="118" width="18" height="10" fill="{EAR}"/>
  <rect x="242" y="118" width="18" height="10" fill="{EAR}"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="210" viewBox="0 0 800 210">
  <!-- background -->
  <rect width="800" height="210" rx="8" fill="{BG}"/>
  <!-- border -->
  <rect x="1" y="1" width="798" height="208" rx="7" fill="none" stroke="{BORDER}" stroke-width="1.5"/>

  <!-- title bar -->
  <line x1="8"   y1="14" x2="130" y2="14" stroke="{ACCENT}" stroke-width="1"/>
  <text x="135"  y="19" font-family="Courier New,Courier,monospace" font-size="11.5" fill="{ACCENT}" font-weight="bold">Xinyu Geng \xb7 PhD Researcher \xb7 AI Security</text>
  <line x1="435" y1="14" x2="792" y2="14" stroke="{ACCENT}" stroke-width="1"/>
  <line x1="1"   y1="26" x2="799" y2="26" stroke="{BORDER}" stroke-width="0.7" opacity="0.35"/>

  <!-- vertical divider -->
  <line x1="460" y1="26" x2="460" y2="209" stroke="{BORDER}" stroke-width="0.7" opacity="0.4"/>

  <!-- horizontal divider (right panel) -->
  <line x1="460" y1="118" x2="799" y2="118" stroke="{BORDER}" stroke-width="0.6" opacity="0.35"/>

  <!-- ══════════ LEFT PANEL ══════════ -->
  <text x="230" y="52" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="13"
        fill="{TEXT}" font-weight="bold">Welcome back, Xinyu!</text>
{dog}
  <!-- links -->
  <text x="230" y="138" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{ACCENT}">shin-resume.vercel.app</text>
  <text x="230" y="155" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">github.com/CHLCCGA</text>
  <text x="230" y="172" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">linkedin.com/in/xinyu-geng</text>
  <text x="230" y="189" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">AGH Krakow \xb7 PhD</text>
  <text x="230" y="205" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10" fill="{DIM}">LLMs under Adversarial Attacks</text>

  <!-- ══════════ RIGHT PANEL ══════════ -->

  <!-- AI news heading -->
  <text x="474" y="45"
        font-family="Courier New,Courier,monospace" font-size="11.5"
        fill="{ACCENT}" font-weight="bold">AI News</text>
  <text x="474" y="63"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{n[0]}</text>
  <text x="474" y="79"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{n[1]}</text>
  <text x="474" y="95"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{n[2]}</text>
  <text x="474" y="110"
        font-family="Courier New,Courier,monospace" font-size="9.5"
        fill="{DIM}" font-style="italic">via huggingface.co/blog</text>

  <!-- trending heading -->
  <text x="474" y="136"
        font-family="Courier New,Courier,monospace" font-size="11.5"
        fill="{ACCENT}" font-weight="bold">GitHub Trending Today</text>
  <text x="474" y="154"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{t[0]}</text>
  <text x="474" y="170"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{t[1]}</text>
  <text x="474" y="186"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{t[2]}</text>
  <text x="474" y="203"
        font-family="Courier New,Courier,monospace" font-size="9.5"
        fill="{DIM}" font-style="italic">Updated daily \xb7 github.com/trending</text>
</svg>"""


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ai_news  = fetch_ai_news()
    trending = fetch_trending()
    svg = generate_svg(ai_news, trending)
    out = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "profile-card.svg")
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Written: {out}")
