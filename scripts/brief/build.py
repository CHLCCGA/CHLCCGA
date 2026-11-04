"""Build one CHLCCGA brief JSON issue."""
import argparse
import calendar
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
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


def _urls(block, issue_date):
    """A url with {y}/{m}/{mm}/{last} placeholders is fetched for the issue's month and the next one;
    a list of urls is fetched as it is (one parser reads them all)."""
    if isinstance(block["url"], list):
        return block["url"]
    if "{" not in block["url"]:
        return [block["url"]]
    day = date.fromisoformat(issue_date)
    urls = []
    for k in range(2):
        y, m = day.year + (day.month - 1 + k) // 12, (day.month - 1 + k) % 12 + 1
        urls.append(block["url"].format(y=y, m=m, mm=f"{m:02d}", last=calendar.monthrange(y, m)[1]))
    return urls


def _events(entries, issue_date, cfg):
    """Keep one venue's performances in the next `days` days and merge repeats of a work into one item.

    A parser returns performances {title, url, at: "YYYY-MM-DD[THH:MM]", en?} or runs
    {title, url, start, end} (festivals), with optional place / tag / summary. Same title and summary =
    same work (a hall's "Koncert symfoniczny" on two dates is two programmes, told apart by the summary);
    same title and start = same run (one festival listed on two pages)."""
    first = date.fromisoformat(issue_date)
    last = first + timedelta(days=cfg.get("days", 14))
    works = {}
    for entry in entries:
        if entry.get("start"):
            if (entry.get("end") or entry["start"]) < first.isoformat() or entry["start"] > last.isoformat():
                continue
            key = ("run", entry["title"].casefold(), entry["start"])
        else:
            if not first.isoformat() <= entry["at"][:10] <= last.isoformat():
                continue
            key = ("show", entry["title"].casefold(), (entry.get("summary") or "").casefold())
        work = works.get(key)
        if work is None:
            work = works[key] = {k: entry[k] for k in ("title", "url", "place", "tag", "summary", "start", "end") if entry.get(k)}
        if "at" in entry:
            shows = work.setdefault("shows", [])
            if all(show["at"] != entry["at"] for show in shows):
                shows.append({"at": entry["at"], **({"en": True} if entry.get("en") else {})})
    items = list(works.values())
    for work in items:
        work.get("shows", []).sort(key=lambda show: show["at"])
    items.sort(key=lambda work: work["shows"][0]["at"] if "shows" in work else max(work["start"], issue_date))
    return items[:cfg.get("limit", 10)]


def _watch(config, pages):
    """For each watched film, look for its pattern in the visible text of its pages (Warsaw cinemas, distributor)."""
    result = []
    for watch in config.get("watch", []):
        pattern = re.compile(watch["pattern"], re.I)
        checked, hits = [], []
        for name, url in watch["urls"].items():
            checked.append({"name": name, "url": url, "ok": url in pages})
            if url not in pages:
                continue
            text = parsers.page_text(pages[url])
            for match in list(pattern.finditer(text))[:2]:
                hits.append({"name": name, "url": url, "text": text[max(0, match.start() - 80):match.end() + 80]})
        result.append({**{key: watch[key] for key in ("id", "name", "link", "asof", "note", "sources") if key in watch},
                       "checked": checked, "hits": hits[:6]})
    return result


def _load_pages(config, fixtures, issue_date):
    urls = {url for block in config["blocks"] for url in _urls(block, issue_date)}
    urls |= {url for watch in config.get("watch", []) for url in watch["urls"].values()}
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


def _recent(out, count=3):
    """The newest issues already written (about a week), whose translations the new issue reuses."""
    issues = []
    for path in sorted(out.glob("????-??-??.json"), reverse=True)[:count]:
        try:
            issues.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return issues


def build(args):
    out = Path(args.out).resolve() if args.out else REPO_DIR / "brief" / "data"
    out.mkdir(parents=True, exist_ok=True)
    if args.translate_only:
        path = out / f"{args.translate_only}.json"
        issue = json.loads(path.read_text(encoding="utf-8"))
        translate_issue(issue, _recent(out))
        _write_json(path, issue)
        _index(out)
        return 0
    config = yaml.safe_load((SCRIPT_DIR / "sources.yaml").read_text(encoding="utf-8"))
    issue_date = args.date or datetime.now(ZoneInfo("Europe/Warsaw")).date().isoformat()
    fetched_at = datetime.now(timezone.utc)
    pages, fetch_errors = _load_pages(config, args.fixtures, issue_date)
    blocks = []
    for cfg in config["blocks"]:
        block = {key: cfg[key] for key in ("id", "name", "group", "kind", "home", "lang")}
        block.update({"status": "ok", "error": None, "items": []})
        urls = [url for url in _urls(cfg, issue_date) if url in pages]
        if not urls:
            block.update({"status": "fail", "error": fetch_errors[_urls(cfg, issue_date)[0]]})
        else:
            try:
                # Parsers resolve links against cfg["url"], so give them the page actually fetched.
                items = [item for url in urls for item in getattr(parsers, cfg["parser"])(pages[url], dict(cfg, url=url), fetched_at)]
                if cfg["kind"] == "events":
                    found, items = bool(items), _events(items, issue_date, cfg)
                    if not items and (found or cfg.get("seasonal")):
                        block["status"] = "idle"   # nothing in the next two weeks (or festival off-season)
                for index, item in enumerate(items):
                    item["id"] = f"{cfg['id']}-{index}"
                if not items and block["status"] != "idle":
                    raise RuntimeError("parsed 0 items (page layout may have changed)")
                block["items"] = items
            except Exception as exc:
                block.update({"status": "fail", "error": str(exc), "items": []})
        if cfg["id"] == "bankier" and block["status"] == "ok":
            _bank_changes(block, out, issue_date)
        blocks.append(block)
    issue = {"date": issue_date, "generated_at": fetched_at.isoformat().replace("+00:00", "Z"), "groups": config["groups"], "translation": {},
             "blocks": blocks, "watch": _watch(config, pages)}
    if args.no_translate:
        issue["translation"] = {"done": 0, "missing": len(_needed(issue)), "error": "skipped"}
    else:
        translate_issue(issue, _recent(out))
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
