"""Small parsers for the source pages configured in sources.yaml."""
import json
import re
from datetime import timedelta, timezone
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


def _text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _absolute(url, base):
    return urljoin(base, url) if url else ""


def _relative_time(value, fetched_at):
    if fetched_at is None:
        return None
    value = (value or "").lower().strip()
    if value in ("just now", "now"):
        return fetched_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    match = re.search(r"(\d+)\s*(minute|minutes|min|m|hour|hours|h|day|days|d)", value)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    if unit.startswith("m") and unit not in ("month",):
        delta = timedelta(minutes=amount)
    elif unit.startswith("h") or unit.startswith("hour"):
        delta = timedelta(hours=amount)
    else:
        delta = timedelta(days=amount)
    return (fetched_at - delta).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_upstract_url(url):
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not (key == "ref" and value == "upstract.com")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _upstract_section(soup, name):
    heading = next((h for h in soup.find_all("h4") if _text(h) == name), None)
    return heading.find_parent(id=True) if heading else None


def upstract(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    section = _upstract_section(soup, block_cfg["section"])
    if not section:
        return []
    items = []
    for li in section.select("li"):
        link = li.find("a", recursive=False)
        if not link or "lmr" in (link.get("class") or []):
            continue
        title = _text(link)
        if not title:
            continue
        # Prefer the "Original Thread" link (Reddit posts), then the headline link. Without a login
        # upstract hides some of these behind /login; then use its public share page /x/<id>, which
        # shows the original link to a human.
        thread = li.find("a", class_="au")
        real = [a.get("href", "") for a in (thread, link) if a is not None and a.get("href", "").startswith("http")]
        item = {"title": title}
        if real:
            item["url"] = _clean_upstract_url(real[0])
        elif link.get("id"):
            item["url"] = f"https://upstract.com/x/{link['id']}"
            item["gated"] = True
        else:
            continue
        stamp = _relative_time(link.get("data-ts"), fetched_at)
        if stamp:
            item["time"] = stamp
        sub = re.match(r"Via (r/\w+)", link.get("data-p", ""))
        if sub:
            item["source"] = sub.group(1)
        items.append(item)
    return items[:block_cfg.get("limit", 10)]


def upstract_x_trends(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    section = _upstract_section(soup, block_cfg["section"])
    if not section:
        return []
    items = []
    for link in section.select("a.tag[href]"):
        query = parse_qs(urlsplit(link["href"]).query).get("q", [""])[0]
        if query:
            items.append({"title": query, "url": _absolute(link["href"], "https://x.com/")})
    return items[:block_cfg.get("limit", 10)]


def upstract_google_trends(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    section = _upstract_section(soup, block_cfg["section"])
    if not section:
        return []
    items = []
    for link in section.select("a.trend-card[href]"):
        title = _text(link.find("h5"))
        if not title:
            continue
        item = {"title": title, "url": _absolute(link["href"], "https://upstract.com/")}
        publisher = _text(link.select_one(".trend-publisher"))
        traffic = _text(link.select_one(".trend-traffic"))
        if publisher:
            item["source"] = publisher
        if traffic:
            item["traffic"] = re.sub(r"^.*?\s(?=\d)", "", traffic).replace(" searches", "")
        items.append(item)
    return items[:block_cfg.get("limit", 10)]


def upstract_otd(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    section = _upstract_section(soup, block_cfg["section"])
    if not section:
        return []
    items = []
    for li in section.select(".wiki_content li"):
        first = li.find("a")
        if not first or not re.fullmatch(r"\d{1,4}", _text(first)):
            continue
        target = li.select_one("strong a") or first.find_next("a") or first
        sentence = " ".join(li.get_text().split())
        sentence = re.sub(r"^\d{1,4}\s*[–-]\s*", "", sentence).replace(" (pictured)", "")
        url = _absolute(target.get("href"), "https://en.wikipedia.org/").replace("http://", "https://", 1)
        items.append({"year": int(_text(first)), "title": sentence, "url": url})
    return items


def tophub(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".rank-all-item table tr")
    items = []
    for row in rows:
        links = row.find_all("a", href=True)
        if not links:
            continue
        link = links[0]
        title = _text(link)
        if not title:
            continue
        item = {"title": title, "url": _absolute(link["href"], "https://tophub.today/")}
        cells = row.find_all("td")
        if len(cells) > 2 and _text(cells[2]):
            item["source"] = _text(cells[2])
        items.append(item)
    return items[:block_cfg.get("limit", 10)]


def _alltop_article(article, base, fetched_at):
    title_link = article.select_one("h2 a, h3 a")
    if not title_link:
        return None
    item = {"title": _text(title_link), "url": _absolute(title_link.get("href"), base)}
    meta = article.select_one("div")
    meta_text = _text(meta)
    source = (meta.find("a") or meta.find("span")) if meta else None
    if source and _text(source):
        item["source"] = _text(source)
    time_match = re.search(r"(?:updated\s*)?(\d+\s*[hmd])\s*ago", meta_text, re.I)
    if time_match:
        item["time"] = _relative_time(time_match.group(1) + " ago", fetched_at)
    count = re.search(r"(\d+)\s*sources", meta_text, re.I)
    if count:
        item["count"] = int(count.group(1))
    return item


def alltop_section(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for article in soup.select("article"):
        item = _alltop_article(article, block_cfg["url"], fetched_at)
        if not item:
            continue
        items.append(item)
    return items[:block_cfg.get("limit", 10)]


def alltop_threads(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    story = soup.select_one("section article")
    if story:
        title_link = story.select_one("h2 a")
        if title_link:
            meta = story.select_one("div")
            item = {"title": _text(title_link), "url": _absolute(title_link.get("href"), block_cfg["url"]), "tag": "Story of the Day"}
            summary = _text(story.select_one("h2 + p"))
            source = _text(meta.find("a")) if meta and meta.find("a") else ""
            count = re.search(r"(\d+)\s*sources", _text(meta), re.I)
            if summary:
                item["summary"] = summary
            if source:
                item["source"] = source
            if count:
                item["count"] = int(count.group(1))
            items.append(item)
    threads_section = next((s for s in soup.select("section") if "Today's Threads" in _text(s.select_one("div"))), None)
    if threads_section:
        for card in threads_section.select("div.group"):
            title_link = card.select_one("h3 a")
            tag_link = card.select_one("a[href^='/']")
            if not title_link or not tag_link:
                continue
            count = re.search(r"(\d+)\s*stories", _text(card), re.I)
            # The headline links to the thread's lead article; the tag links to the category page.
            item = {"title": _text(title_link), "url": _absolute(title_link.get("href"), block_cfg["url"]), "tag": _text(tag_link)}
            summary = _text(card.select_one("h3 + p"))
            if summary:
                item["summary"] = summary
            if count:
                item["count"] = int(count.group(1))
            items.append(item)
    return items


def pepper(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for article in soup.select("article"):
        data_node = next((n for n in article.select("[data-vue3]") if "ThreadMainListItemNormalizer" in n.get("data-vue3", "")), None)
        if not data_node:
            continue
        try:
            thread = json.loads(data_node["data-vue3"])["props"]["thread"]
        except (KeyError, ValueError, TypeError):
            continue
        if thread.get("isPinned"):
            continue
        title_link = article.select_one(".thread-title a[href]")
        if not title_link:
            continue
        merchant = (thread.get("merchant") or {}).get("merchantName") or thread.get("linkHost")
        item = {
            "title": " ".join((thread.get("title") or _text(title_link)).split()),
            "url": _absolute(title_link["href"], block_cfg["url"]),
            "temperature": int(round(float(thread.get("temperature") or 0))),
            "price_old": thread.get("nextBestPrice") or None,
            "currency": block_cfg["currency"],
            "expired": bool(thread.get("isExpired")),
            "comments": int(thread.get("commentCount") or 0),
        }
        if thread.get("type"):
            item["type"] = thread["type"]
        if thread.get("price"):
            item["price"] = thread["price"]
        if merchant:
            item["merchant"] = merchant
        items.append(item)
        if len(items) >= block_cfg.get("limit", 10):
            break
    return items


def bankier(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select(".offers__container .offers__item"):
        name = _text(card.select_one(".offers__item-content-name"))
        rank_text = _text(card.select_one(".offers__item-header-index"))
        rank_match = re.search(r"\d+", rank_text)
        if not name or not rank_match:
            continue
        bank, product = (name.split(" - ", 1) + [""])[:2]
        item = {"rank": int(rank_match.group()), "title": name, "bank": bank, "product": product, "promoted": False, "bonus_max": None}
        label = _text(card.select_one(".offers__item-special-label"))
        if label:
            item["label"] = label
            item["promoted"] = "promowana" in label.lower()
        for attribute in card.select(".offers__item-content-attribute"):
            label_text = _text(attribute.select_one(".offers__item-content-attribute-label"))
            value = _text(attribute.select_one(".offers__item-content-attribute-value"))
            if label_text.startswith("Konto") and value:
                item["account_fee"] = value
            if label_text.startswith("Bonus"):
                if value and value.lower() != "brak":
                    number = re.search(r"([\d\s]+)", value)
                    if number:
                        item["bonus_max"] = int(number.group(1).replace(" ", ""))
                    detail = _text(attribute.select_one(".tooltip__content"))[:600]
                    if detail:
                        item["bonus_text"] = detail
        offer = next((a for a in card.select("a[href]") if "ofert" in _text(a).lower()), None)
        item["url"] = _absolute(offer.get("href") if offer else "", block_cfg["url"]) or block_cfg["url"]
        items.append(item)
    return items
