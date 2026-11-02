"""Build one CHLCCGA brief JSON issue."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

import parsers
from translate import _needed, translate_issue

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parents[1]
USER_AGENT = "Mozilla/5.0 (compatible; CHLCCGA-brief/1.0; +https://github.com/CHLCCGA/CHLCCGA)"


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _fetch(url):
    error = None
    for attempt in range(2):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            if response.status_code < 500:
                response.raise_for_status()
                return response.text
            error = RuntimeError(f"HTTP {response.status_code}")
        except Exception as exc:
            error = exc
        if attempt == 0:
            time.sleep(5)
    raise error


def _load_pages(config, fixtures):
    urls = {block["url"] for block in config["blocks"]}
    pages, errors = {}, {}
    if fixtures:
        fixtures = Path(fixtures).resolve()
        manifest = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
        for url in urls:
            try:
                pages[url] = (fixtures / manifest[url]).read_text(encoding="utf-8")
            except Exception as exc:
                errors[url] = str(exc)
        return pages, errors
    for url in urls:
        try:
            pages[url] = _fetch(url)
        except Exception as exc:
            errors[url] = str(exc)
    return pages, errors


def _previous_bank(out, issue_date):
    candidates = sorted((path for path in out.glob("????-??-??.json") if path.stem < issue_date), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            block = next(b for b in data["blocks"] if b["id"] == "bankier")
            if block["status"] == "ok":
                return path.stem, block
        except (OSError, ValueError, KeyError, StopIteration):
            continue
    return None, None


def _bank_changes(block, out, issue_date):
    previous_date, previous = _previous_bank(out, issue_date)
    changes = {"prev": previous_date, "added": [], "removed": [], "moved": [], "bonus": []}
    if not previous:
        block["changes"] = changes
        return
    old = {item["title"]: item for item in previous["items"]}
    new = {item["title"]: item for item in block["items"]}
    changes["added"] = [{"title": item["title"], "rank": item["rank"]} for item in block["items"] if item["title"] not in old]
    changes["removed"] = [{"title": item["title"], "rank": item["rank"]} for item in previous["items"] if item["title"] not in new]
    for item in block["items"]:
        before = old.get(item["title"])
        if not before:
            continue
        if before["rank"] != item["rank"]:
            changes["moved"].append({"title": item["title"], "from": before["rank"], "to": item["rank"]})
        if before.get("bonus_max") != item.get("bonus_max"):
            changes["bonus"].append({"title": item["title"], "from": before.get("bonus_max"), "to": item.get("bonus_max")})
    block["changes"] = changes


def _index(out):
    dates = sorted((path.stem for path in out.glob("????-??-??.json")), reverse=True)
    _write_json(out / "index.json", dates)


def build(args):
    out = Path(args.out).resolve() if args.out else REPO_DIR / "brief" / "data"
    out.mkdir(parents=True, exist_ok=True)
    if args.translate_only:
        path = out / f"{args.translate_only}.json"
        issue = json.loads(path.read_text(encoding="utf-8"))
        translate_issue(issue)
        _write_json(path, issue)
        _index(out)
        return 0
    config = yaml.safe_load((SCRIPT_DIR / "sources.yaml").read_text(encoding="utf-8"))
    issue_date = args.date or datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
    fetched_at = datetime.now(timezone.utc)
    pages, fetch_errors = _load_pages(config, args.fixtures)
    blocks = []
    for cfg in config["blocks"]:
        block = {key: cfg[key] for key in ("id", "name", "group", "kind", "home", "lang")}
        block.update({"status": "ok", "error": None, "items": []})
        if cfg["url"] in fetch_errors:
            block.update({"status": "fail", "error": fetch_errors[cfg["url"]]})
        else:
            try:
                items = getattr(parsers, cfg["parser"])(pages[cfg["url"]], cfg, fetched_at)
                for index, item in enumerate(items):
                    item["id"] = f"{cfg['id']}-{index}"
                if not items:
                    raise RuntimeError("parsed 0 items (page layout may have changed)")
                block["items"] = items
            except Exception as exc:
                block.update({"status": "fail", "error": str(exc), "items": []})
        if cfg["id"] == "bankier" and block["status"] == "ok":
            _bank_changes(block, out, issue_date)
        blocks.append(block)
    issue = {"date": issue_date, "generated_at": fetched_at.isoformat().replace("+00:00", "Z"), "groups": config["groups"], "translation": {}, "blocks": blocks}
    if args.no_translate:
        issue["translation"] = {"done": 0, "missing": len(_needed(issue)), "error": "skipped"}
    else:
        translate_issue(issue)
    _write_json(out / f"{issue_date}.json", issue)
    _index(out)
    return 0 if any(block["status"] == "ok" for block in blocks) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures")
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--translate-only")
    parser.add_argument("--out")
    parser.add_argument("--date")
    return build(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
