"""Write news/data/index.json: the digest dates the site can show, newest first.

Only daily files (YYYY-MM-DD.json) are listed; the old weekly 2026-Wnn.json
files and the per-run YYYY-MM-DD.sources.json files are skipped.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "news" / "data"
DAILY = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

dates = sorted((p.stem for p in DATA_DIR.iterdir() if DAILY.match(p.name)), reverse=True)
(DATA_DIR / "index.json").write_text(json.dumps(dates, indent=1) + "\n", encoding="utf-8")
print(f"index.json: {len(dates)} dates, latest {dates[0] if dates else '-'}")
