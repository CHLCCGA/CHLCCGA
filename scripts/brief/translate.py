"""DeepSeek translation for a brief issue dictionary."""
import json
import os

import requests

ENDPOINT = "https://api.deepseek.com/chat/completions"


def _needed(issue):
    fields = []
    for block in issue["blocks"]:
        if block["lang"] == "zh" or block["status"] != "ok":
            continue
        for item in block["items"]:
            if "title_zh" not in item:
                fields.append((item, "title", "title_zh", "headline"))
            if item.get("summary") and "summary_zh" not in item:
                fields.append((item, "summary", "summary_zh", "headline"))
            if block["kind"] == "bank" and item.get("bonus_text") and "bonus_zh" not in item:
                fields.append((item, "bonus_text", "bonus_zh", "bonus"))
    return fields


def _request(strings, style, key):
    instruction = (
        "Translate each string into concise natural Simplified Chinese. Keep well-known names in their standard Chinese form or original. "
        "Hashtags or handles written in Latin letters that are names or brands may stay as they are; translate those in any other script (e.g. Arabic) into Chinese, keeping a leading #. "
        "Return only JSON object {\"t\":[...]} in the same order, with no commentary."
    )
    if style == "bonus":
        instruction = (
            "For each Polish bank bonus description, write a concise Simplified Chinese summary (at most 60 Chinese characters) containing the bonus amount(s) and main conditions. "
            "Return only JSON object {\"t\":[...]} in the same order, with no commentary."
        )
    response = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "deepseek-v4-flash", "response_format": {"type": "json_object"}, "messages": [
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


def translate_issue(issue):
    """Fill translations in place and set the contract's translation summary."""
    needed = _needed(issue)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        issue["translation"] = {"done": 0, "missing": len(needed), "error": "DEEPSEEK_API_KEY is not set"}
        return issue["translation"]
    first_error = None
    for style in ("headline", "bonus"):
        entries = [entry for entry in needed if entry[3] == style]
        for start in range(0, len(entries), 50):
            batch = entries[start:start + 50]
            strings = [entry[0][entry[1]] for entry in batch]
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
    total = len(needed)
    issue["translation"] = {"done": total - missing, "missing": missing, "error": first_error if missing else None}
    return issue["translation"]
