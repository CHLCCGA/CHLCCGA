#!/usr/bin/env python3
"""Generate GitHub profile card SVG with dynamic GitHub trending repos."""

import urllib.request
import json
import datetime
import os
import html

# ── Tips (rotate by day-of-year) ─────────────────────────────────────────────
TIPS = [
    ("Adversarial Robustness",
     "Map the full attack surface",
     "before red-teaming your LLM."),
    ("Prompt Injection",
     "Indirect injections via tool",
     "output are the blind spot."),
    ("Multi-Agent Security",
     "Every agent hop introduces",
     "a new trust boundary."),
    ("Jailbreak Defense",
     "Representation engineering",
     "outperforms prompt filtering."),
    ("LLM Evaluation",
     "Benchmark on adversarial sets,",
     "not just standard benchmarks."),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def esc(text: str) -> str:
    return html.escape(str(text), quote=False)

def trunc(text: str, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"

def stars_fmt(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)

# ── Fetch trending ─────────────────────────────────────────────────────────────
def fetch_trending():
    since = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    url = (
        f"https://api.github.com/search/repositories"
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
        print(f"Warning: could not fetch trending ({e}), using placeholders.")
        return [
            ("anthropics/claude-code", 12300),
            ("huggingface/smollm3", 8700),
            ("openai/openai-agents", 6100),
        ]

# ── SVG generation ─────────────────────────────────────────────────────────────
def generate_svg(trending) -> str:
    # Rotate tip daily
    tip_idx = datetime.date.today().timetuple().tm_yday % len(TIPS)
    tip_title, tip_l1, tip_l2 = TIPS[tip_idx]

    # Trending lines (right-pad to 3)
    t = [f"★{stars_fmt(s)}  {trunc(esc(name), 25)}" for name, s in trending]
    while len(t) < 3:
        t.append("")

    # Palette (Claude Code terminal)
    BG     = "#0D0D0D"
    BORDER = "#DA7756"
    ACCENT = "#DA7756"
    TEXT   = "#E0E0E0"
    DIM    = "#6E6E6E"
    DARK   = "#1A0800"

    # ── pixel mascot rects (9-pixel-wide grid, each pixel=8px, centered at x=230) ──
    # Head center at x=230 → starts at x=194, width=72
    mascot = f"""
  <!-- antennae -->
  <rect x="210" y="62" width="8" height="9" fill="{ACCENT}"/>
  <rect x="242" y="62" width="8" height="9" fill="{ACCENT}"/>
  <!-- head solid block -->
  <rect x="194" y="71" width="72" height="20" fill="{ACCENT}"/>
  <!-- eyes (dark overlay) -->
  <rect x="209" y="78" width="14" height="11" fill="{DARK}"/>
  <rect x="237" y="78" width="14" height="11" fill="{DARK}"/>
  <!-- body -->
  <rect x="194" y="91" width="72" height="18" fill="{ACCENT}"/>
  <!-- feet -->
  <rect x="194" y="109" width="22" height="9" fill="{ACCENT}"/>
  <rect x="244" y="109" width="22" height="9" fill="{ACCENT}"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="210" viewBox="0 0 800 210">
  <!-- background -->
  <rect width="800" height="210" rx="8" fill="{BG}"/>
  <!-- border -->
  <rect x="1" y="1" width="798" height="208" rx="7" fill="none" stroke="{BORDER}" stroke-width="1.5"/>

  <!-- title bar -->
  <line x1="8"   y1="14" x2="155" y2="14" stroke="{ACCENT}" stroke-width="1"/>
  <text x="160"  y="19" font-family="Courier New,Courier,monospace" font-size="11.5" fill="{ACCENT}" font-weight="bold">Claude Code \xb7 Xinyu&#39;s GitHub</text>
  <line x1="380" y1="14" x2="792" y2="14" stroke="{ACCENT}" stroke-width="1"/>
  <line x1="1"   y1="26" x2="799" y2="26" stroke="{BORDER}" stroke-width="0.7" opacity="0.35"/>

  <!-- vertical divider -->
  <line x1="460" y1="26" x2="460" y2="209" stroke="{BORDER}" stroke-width="0.7" opacity="0.4"/>

  <!-- horizontal divider (right panel) -->
  <line x1="460" y1="118" x2="799" y2="118" stroke="{BORDER}" stroke-width="0.6" opacity="0.35"/>

  <!-- ══════════ LEFT PANEL ══════════ -->

  <!-- welcome -->
  <text x="230" y="52" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="13"
        fill="{TEXT}" font-weight="bold">Welcome back, Xinyu!</text>
{mascot}
  <!-- links -->
  <text x="230" y="135" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{ACCENT}">shin-resume.vercel.app</text>
  <text x="230" y="152" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">github.com/CHLCCGA</text>
  <text x="230" y="169" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">linkedin.com/in/xinyu-geng</text>
  <text x="230" y="186" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{DIM}">AGH Krakow \xb7 PhD Researcher</text>
  <text x="230" y="203" text-anchor="middle"
        font-family="Courier New,Courier,monospace" font-size="10" fill="{DIM}">LLMs under Adversarial Attacks</text>

  <!-- ══════════ RIGHT PANEL ══════════ -->

  <!-- tips heading -->
  <text x="474" y="45"
        font-family="Courier New,Courier,monospace" font-size="11.5"
        fill="{ACCENT}" font-weight="bold">Research Tips</text>
  <text x="474" y="63"
        font-family="Courier New,Courier,monospace" font-size="10.5"
        fill="{TEXT}" font-weight="bold">{esc(tip_title)}</text>
  <text x="474" y="79"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{esc(tip_l1)}</text>
  <text x="474" y="95"
        font-family="Courier New,Courier,monospace" font-size="10.5" fill="{TEXT}">{esc(tip_l2)}</text>
  <text x="474" y="110"
        font-family="Courier New,Courier,monospace" font-size="9.5"
        fill="{DIM}" font-style="italic">/research-notes for more</text>

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
    trending = fetch_trending()
    svg = generate_svg(trending)
    out = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "profile-card.svg")
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Written: {out}")
