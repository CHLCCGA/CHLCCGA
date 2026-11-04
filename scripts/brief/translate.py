"""DeepSeek translation for a brief issue dictionary."""
import json
import os

import requests

ENDPOINT = "https://api.deepseek.com/chat/completions"


def _fields(issue):
    """Every translatable field of an issue, translated or not: (item, source field, target field, style)."""
    for block in issue["blocks"]:
        if block["lang"] == "zh" or block["status"] != "ok":
            continue
        events = block["kind"] == "events"
        for item in block["items"]:
            yield item, "title", "title_zh", "event" if events else "headline"
            if item.get("summary"):
                yield item, "summary", "summary_zh", "headline"
            if events and item.get("tag"):
                yield item, "tag", "tag_zh", "headline"
            if block["kind"] == "bank" and item.get("bonus_text"):
                yield item, "bonus_text", "bonus_zh", "bonus"


def _needed(issue):
    return [entry for entry in _fields(issue) if entry[2] not in entry[0]]


def _key(entry):
    return entry[3], json.dumps(_sent_text(entry), ensure_ascii=False)


def reuse(issue, previous):
    """Copy translations of strings unchanged since earlier issues, so a long-running show or an unchanged bank
    bonus keeps the same Chinese text and is not paid for again. Returns how many were filled."""
    known = {_key(entry): entry[0][entry[2]] for old in previous for entry in _fields(old) if entry[2] in entry[0]}
    count = 0
    for entry in _needed(issue):
        if _key(entry) in known:
            entry[0][entry[2]] = known[_key(entry)]
            count += 1
    return count


INSTRUCTIONS = {
    "headline": "Translate each string into concise natural Simplified Chinese. Keep well-known names in their standard Chinese form or original. "
                "Hashtags or handles written in Latin letters that are names or brands may stay as they are; translate those in any other script (e.g. Arabic) into Chinese, keeping a leading #. ",
    # Titles of films, plays, operas and concerts at Warsaw venues, sent with their description (director,
    # composer...) so a known work gets its usual Chinese title rather than a word-for-word one. As one string
    # "title — description" the model translated both into the title (2026-11-04), so they go as two fields.
    "event": "Each item is an object: `title` is the Polish title of a film, play, opera, ballet, concert or festival in Warsaw; "
             "`about` (may be empty) describes it and is context only. For each item return just the title in Simplified Chinese, "
             "never any part of `about`. If it is a well-known work and you are sure of its usual Chinese title, use that; "
             "otherwise translate the title naturally. Keep names of people, bands and brands as they are. ",
    "bonus": "For each Polish bank bonus description, write a concise Simplified Chinese summary (at most 60 Chinese characters) containing the bonus amount(s) and main conditions. ",
}


def _request(strings, style, key):
    instruction = INSTRUCTIONS[style] + "Return only JSON object {\"t\":[...]} in the same order, with no commentary."
    response = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        # Headlines (and event titles) translate as well without thinking at ~1/7 of the tokens; the bank summaries
        # keep it, since without it they drop the conditions (measured 2026-11-02).
        json={"model": "deepseek-flash", "thinking": {"type": "enabled" if style == "bonus" else "disabled"},
              "response_format": {"type": "json_object"}, "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(strings, ensure_ascii=False)},
        ]},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
        translated = json.loads(payload["choices"][0]["message"]["content"])["t"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid DeepSeek response: {exc}") from exc
    if not isinstance(translated, list):
        raise RuntimeError("invalid DeepSeek response: t is not an array")
    return translated


def _sent_text(entry):
    item, field, _target, style = entry
    if style == "event":
        return {"title": item[field], "about": item.get("summary", "")}
    return item[field]


def translate_issue(issue, previous=()):
    """Fill translations in place (reusing those of `previous` issues first) and set the translation summary."""
    reused = reuse(issue, previous)
    needed = _needed(issue)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        issue["translation"] = {"done": reused, "reused": reused, "missing": len(needed), "error": "DEEPSEEK_API_KEY is not set"}
        return issue["translation"]
    first_error = None
    for style in INSTRUCTIONS:
        entries = [entry for entry in needed if entry[3] == style]
        for start in range(0, len(entries), 50):
            batch = entries[start:start + 50]
            strings = [_sent_text(entry) for entry in batch]
            translations = None
            for attempt in range(2):
                try:
                    candidate = _request(strings, style, key)
                    if len(candidate) != len(batch):
                        raise RuntimeError(f"DeepSeek returned {len(candidate)} translations for {len(batch)} strings")
                    translations = candidate
                    break
                except Exception as exc:  # an API failure must not stop the issue build
                    if first_error is None:
                        first_error = str(exc)
            if translations is not None:
                for (item, _source, target, _style), translated in zip(batch, translations):
                    if isinstance(translated, str) and translated.strip():
                        item[target] = translated.strip()
    missing = len(_needed(issue))
    total = len(needed) + reused
    issue["translation"] = {"done": total - missing, "reused": reused, "missing": missing, "error": first_error if missing else None}
    return issue["translation"]
