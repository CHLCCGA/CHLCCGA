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


# Venue programme pages -------------------------------------------------------

_PL_MONTHS = {
    "sty": 1, "stycz": 1, "lut": 2, "luty": 2, "mar": 3, "marzec": 3,
    "kwi": 4, "kwiec": 4, "maj": 5, "cze": 6, "czerw": 6, "lip": 7,
    "sier": 8, "sie": 8, "wrz": 9, "wrzes": 9, "paz": 10, "list": 11,
    "lis": 11, "gru": 12, "grudz": 12,
}


def _event_fold(value):
    return " ".join((value or "").lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz")).split())


def _event_month(value):
    value = _event_fold(value).strip(". ,")
    for name, number in _PL_MONTHS.items():
        if value.startswith(name):
            return number
    return None


def _event_day(day, month, fetched_at, year=None):
    """Return an ISO date, choosing the nearby occurrence of a Polish month/day."""
    try:
        day, month = int(day), int(month)
    except (TypeError, ValueError):
        return None
    if year is not None:
        try:
            return fetched_at.replace(year=int(year), month=month, day=day).date().isoformat()
        except ValueError:
            return None
    choices = []
    for candidate_year in (fetched_at.year - 1, fetched_at.year, fetched_at.year + 1):
        try:
            candidate = fetched_at.replace(year=candidate_year, month=month, day=day)
        except ValueError:
            continue
        choices.append(candidate)
    if not choices:
        return None
    return min(choices, key=lambda candidate: abs((candidate.date() - fetched_at.date()).days)).date().isoformat()


def _event_at(day, month, fetched_at, time="", year=None):
    stamp = _event_day(day, month, fetched_at, year)
    if not stamp:
        return None
    match = re.search(r"(\d{1,2})[.:](\d{2})", time or "")
    return f"{stamp}T{int(match.group(1)):02d}:{match.group(2)}" if match else stamp


def _event_url(href, block_cfg):
    url = _absolute(href, block_cfg["url"]) if href else block_cfg["url"]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return block_cfg["url"]
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key.lower() != "mid" and not key.lower().startswith("utm_") and key.lower() != "fbclid"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _event_summary(value, limit=160):
    value = _text(value) if hasattr(value, "get_text") else " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0]


def _event_excluded(value):
    value = _event_fold(value)
    return ("dla grup zorganizowanych" in value or "dla szkol" in value or
            "warsztaty dla szkol" in value or "vod." in value or "tylko online" in value)


def _cfg_month_year(block_cfg, fetched_at):
    query = parse_qs(urlsplit(block_cfg["url"]).query)
    year = (query.get("year") or [""])[0]
    month = (query.get("month") or [""])[0]
    match = re.search(r"date_from=(\d{4})-(\d{1,2})", block_cfg["url"])
    if match:
        year, month = match.groups()
    try:
        return int(year), int(month)
    except ValueError:
        return fetched_at.year, fetched_at.month


def piecsmakow(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    link_cfg = dict(block_cfg, url=base["href"]) if base else block_cfg
    items, seen = [], set()
    for box in soup.select(".boxfilmu"):
        title_link = box.select_one(".ty a[href]")
        title = _text(title_link)
        if not title_link or not title:
            continue
        url = _event_url(title_link["href"], link_cfg)
        key = (title, url)
        if key in seen:
            continue
        seen.add(key)
        summary = _event_summary(box.select_one(".rez"))
        for date in box.select(".kinowe .info-seanse-li span"):
            match = re.search(r"(\d{1,2})\s+([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)\s*/\s*(\d{1,2}:\d{2})", _text(date))
            if not match:
                continue
            month = _event_month(match.group(2))
            at = _event_at(match.group(1), month, fetched_at, match.group(3)) if month else None
            if not at:
                continue
            item = {"title": title, "url": url, "at": at}
            if summary:
                item["summary"] = summary
            items.append(item)
    return items


def muranow_cycle(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select(".movie-cycles-item"):
        title_link = card.select_one(".movie-cycles-intro__title a[href]")
        title = _text(title_link)
        if not title_link or not title:
            continue
        movie = card.select_one(".c-button-tickets--movie-link[href]")
        url = _event_url((movie or title_link)["href"], block_cfg)
        for info in card.select(".movie-cycle-info"):
            date = _text(info.select_one(".movie-cycle-info__date-group"))
            match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date)
            if not match:
                continue
            for time in info.select(".movie-cycle-info__date .date"):
                at = _event_at(match.group(1), match.group(2), fetched_at, _text(time), match.group(3))
                if at:
                    items.append({"title": title, "url": url, "at": at})
    return items


def muranow_festivals(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select("article.node--type-movie-festival"):
        title = _text(card.select_one(".node__title"))
        link = card.select_one(".node__main-link[href]")
        match = re.search(
            r"\|\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s+([^\s|]+)"
            r"(?:\s*[-–]\s*(\d{1,2})\s+([^\s|]+))?\s*$", title)
        if not link or not match:
            continue
        start_month = _event_month(match.group(3))
        end_month = _event_month(match.group(5) or match.group(3))
        if not start_month or not end_month:
            continue
        # The end date's nearest occurrence fixes the year; a start month after the end month is the year before.
        end = _event_day(match.group(4) or match.group(2) or match.group(1), end_month, fetched_at)
        start = end and _event_day(match.group(1), start_month, fetched_at, int(end[:4]) - (start_month > end_month))
        if not start or not end:
            continue
        item = {"title": title[:match.start()].strip(" |"), "url": _event_url(link["href"], block_cfg),
                "start": start, "end": end}
        tag = _text(card.select_one(".node__label-type"))
        if tag:
            item["tag"] = tag
        items.append(item)
    return items


def iluzjon(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for heading in soup.find_all("h3"):
        date_match = re.match(r"\s*(\d{1,2})\s+([^\s-]+)\s*-", _text(heading))
        table = heading.find_next_sibling("table")
        month = _event_month(date_match.group(2)) if date_match else None
        if not date_match or not month or not table:
            continue
        day = _event_day(date_match.group(1), month, fetched_at)
        if not day:
            continue
        for row in table.select("tr"):
            link = row.select_one(".hour a[href]")
            match = re.match(r"\s*(\d{1,2}:\d{2})\s*-\s*(.+)", _text(link)) if link else None
            if not match:
                continue
            text = _text(row)
            if _event_excluded(text):
                continue
            item = {"title": match.group(2), "url": _event_url(link["href"], block_cfg),
                    "at": f"{day}T{match.group(1)}"}
            place = _text(row.select_one(".location")).strip("() ")
            tag = _text(row.select_one(".cycle-info a"))
            summary = _event_summary(" · ".join(_text(node) for node in row.select(".set-info")))
            if place:
                item["place"] = place
            if tag:
                item["tag"] = tag
            if summary:
                item["summary"] = summary
            if "napisy angielskie" in _event_fold(text):
                item["en"] = True
            items.append(item)
    return items


def teatrwielki(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for wrapper in soup.select("#events-list > .data-event"):
        stamp = wrapper.find("time", datetime=True)
        if not stamp:
            continue
        children = []
        event_list = wrapper.find("ul", recursive=False)
        if event_list:
            children = event_list.find_all("li", class_="data-event", recursive=False)
        for event in children or [wrapper]:
            title_link = event.select_one(".event-in h3 a[href]")
            title = _text(title_link)
            text = _text(event)
            if not title_link or not title or _event_excluded(text):
                continue
            hour = _text(event.select_one(".hour"))
            at = stamp["datetime"] + (f"T{hour}" if re.fullmatch(r"\d{1,2}:\d{2}", hour) else "")
            item = {"title": title, "url": _event_url(title_link["href"], block_cfg), "at": at}
            tag = _text(event.select_one(".category"))
            place = _text(event.select_one(".hall"))
            composer = _text(event.select_one("h4"))
            description = _text(event.select_one(".teaser")).split(" | ", 1)[0]
            summary = _event_summary(" · ".join(part for part in (composer, description) if part))
            if tag:
                item["tag"] = tag
            if place:
                item["place"] = place
            if summary:
                item["summary"] = summary
            if "angielskimi napisami" in _event_fold(text):
                item["en"] = True
            items.append(item)
    return items


def narodowy(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    year, month = _cfg_month_year(block_cfg, fetched_at)
    stages = {"kal-1": "Sala Bogusławskiego", "kal-2": "Scena przy Wierzbowej im. Jerzego Grzegorzewskiego",
              "kal-3": "Scena Studio"}
    items = []
    for row in soup.select(".kal-row-wrap"):
        day = _text(row.select_one(".kal-day"))
        for date in row.select(".kal-date"):
            link = date.select_one("a[href]")
            hour = _text(date.find("b"))
            title = _text(link)
            if not link or not title or not re.fullmatch(r"\d{1,2}:\d{2}", hour):
                continue
            column = date.find_parent("div", class_=re.compile(r"^kal-[123]$"))
            info = _text(column.select_one(".kal-info")) if column else ""
            text = " ".join((title, info))
            if _event_excluded(text):
                continue
            at = _event_at(day, month, fetched_at, hour, year)
            if not at:
                continue
            item = {"title": title, "url": _event_url(link["href"], block_cfg), "at": at}
            if column:
                place = stages.get(next((name for name in column.get("class", []) if name in stages), ""))
                if place:
                    item["place"] = place
            if "angielsk" in _event_fold(info) or "english" in _event_fold(info):
                item["en"] = True
            items.append(item)
    return items


def trwarszawa(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for day in soup.select(".trw-calendar-page-day"):
        for event in day.select(".trw-calendar-page-event"):
            link = event.select_one(".trw-calendar-page-event__main[href]")
            time = event.select_one("time[datetime]")
            title = _text(event.select_one(".trw-calendar-page-event__title"))
            text = _text(event)
            if not link or not time or not title or _event_excluded(text):
                continue
            place = _text(event.select_one(".trw-calendar-page-event__place"))
            if "tr on tour" in _event_fold(text) and "warszawa" not in _event_fold(place):
                continue
            at = time["datetime"]
            key = (title, at, link["href"])
            if key in seen:
                continue
            seen.add(key)
            item = {"title": title, "url": _event_url(link["href"], block_cfg), "at": at}
            tag = _text(event.select_one(".trw-calendar-page-event__category"))
            if place:
                item["place"] = place
            if tag:
                item["tag"] = tag
            if "angiel" in _event_fold(text) or "english" in _event_fold(text):
                item["en"] = True
            items.append(item)
    return items


def nowyteatr(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    year, month = _cfg_month_year(block_cfg, fetched_at)
    category_words = ("teatr", "literatura", "muzyka", "spotkania", "akcje", "warsztaty")
    items = []
    for row in soup.select(".calendar__row"):
        day = _text(row.select_one("h3 span"))
        for cell in row.select(".calendar__cell"):
            link = cell.select_one(".calendar__link[href]")
            title = _text(cell.select_one(".calendar__event h4"))
            time = _text(cell.select_one(".calendar__time time"))
            lines = [_text(node) for node in cell.select(".calendar__event h5") if _text(node)]
            text = _text(cell)
            if not link or not title or _event_excluded(text):
                continue
            at = _event_at(day, month, fetched_at, time, year)
            if not at:
                continue
            item = {"title": title, "url": _event_url(link["href"], block_cfg), "at": at}
            categories = next((line for line in lines if any(word in _event_fold(line) for word in category_words)), "")
            summary = next((line for line in lines if line != categories and
                            "subtitle" not in _event_fold(line) and "napisy" not in _event_fold(line) and
                            "audiodeskrypcja" not in _event_fold(line) and "pjm" not in _event_fold(line)), "")
            if categories:
                item["tag"] = categories.replace(" / Wiek", "")
            if summary:
                item["summary"] = _event_summary(summary)
            if "english subtitles" in _event_fold(text):
                item["en"] = True
            items.append(item)
    return items


def teatrpolski(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for show in soup.select(".shedule-item[data-date]"):
        title_link = show.select_one(".shedule-item__header[href]")
        title = _text(show.select_one(".shedule-item__title"))
        day = show.get("data-date")
        if not title_link or not title or not day or _event_excluded(_text(show)):
            continue
        summary = _event_summary(show.select_one(".shedule-item__subtitle"))
        place = _text(show.select_one(".shedule-item__place"))
        tag = _text(show.select_one(".shedule-item__type"))
        for time in show.select(".shedule-time__time-text"):
            hour = _text(time)
            if not re.fullmatch(r"\d{1,2}:\d{2}", hour):
                continue
            item = {"title": title, "url": _event_url(title_link["href"], block_cfg), "at": f"{day}T{hour}"}
            if place:
                item["place"] = place
            if tag:
                item["tag"] = tag
            if summary:
                item["summary"] = summary
            items.append(item)
    return items


def roma(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for calendar_month in soup.select(".month"):
        month = _event_month(_text(calendar_month.select_one(".month-name")))
        if not month:
            continue
        for day in calendar_month.select(".day"):
            number = _text(day.select_one(".day-num"))
            for link in day.select(".spektakleTooltip a[href]"):
                title = _text(link.select_one(".name"))
                hour = _text(link.select_one(".hour"))
                at = _event_at(number, month, fetched_at, hour)
                if title and at:
                    items.append({"title": title, "url": _event_url(link["href"], block_cfg), "at": at})
    return items


def filharmonia(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    # event-list-row is the detailed list.  The same events also appear in a compact calendar.
    for event in soup.select(".event-list-row"):
        link = event.select_one(".event-link[href]")
        title = _text(event.select_one(".event-title"))
        date = _text(event.select_one(".event-date .inner"))
        date_match = re.search(r"(\d{1,2})\.(\d{1,2})", date)
        hour = _text(event.select_one(".day-time .time"))
        if not link or not title or not date_match:
            continue
        at = _event_at(date_match.group(1), date_match.group(2), fetched_at, hour)
        if not at:
            continue
        item = {"title": title, "url": _event_url(link["href"], block_cfg), "at": at}
        tag = _text(event.select_one(".event-categories"))
        place = _text(event.select_one(".event-venue"))
        summary = _event_summary(event.select_one(".event-meta-info"))
        if tag:
            item["tag"] = tag
        if place:
            item["place"] = place
        if summary:
            item["summary"] = summary
        items.append(item)
        seen.add((title, at))
    # The detailed feed in this saved page stops before the end of the calendar.
    # Keep only later compact-calendar entries so already detailed events are not parsed twice.
    for event in soup.select("a.event-list-chocolate[href]"):
        title = _text(event.select_one(".title-attr"))
        date = _text(event.select_one(".event-date span"))
        date_match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", date)
        hour = _text(event.select_one(".day-time .time"))
        if not title or not date_match:
            continue
        at = _event_at(date_match.group(1), date_match.group(2), fetched_at, hour)
        if not at or (title, at) in seen:
            continue
        items.append({"title": title, "url": _event_url(event["href"], block_cfg), "at": at})
        seen.add((title, at))
    return items


def progresja(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for date in soup.select(".startdate"):
        card = date.find_parent("div", class_=re.compile(r"fs-grid-item-\d+-container"))
        if not card:
            continue
        title_link = card.select_one(".cline a.el-link[href]")
        title = _text(title_link)
        month = _event_month(_text(card.select_one(".month")))
        number = _text(date)
        time = next((_text(node) for node in card.select("h5") if re.search(r"\d{1,2}:\d{2}", _text(node))), "")
        year_match = re.search(r"\b(20\d{2})\b", _text(card))
        if not title_link or not title or not month or not year_match:
            continue
        at = _event_at(number, month, fetched_at, time, year_match.group(1))
        if not at:
            continue
        text = _text(card)
        if _event_excluded(text):
            continue
        key = (title, at, title_link["href"])
        if key in seen:
            continue
        seen.add(key)
        item = {"title": title, "url": _event_url(title_link["href"], block_cfg), "at": at}
        place = next((_text(line) for line in card.select(".cline")
                      if _event_fold(_text(line)).startswith("progresja")), "")
        if place:
            item["place"] = place
        items.append(item)
    return items


def stodola(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for event in soup.select("li"):
        date = _text(event.select_one(".edat .date"))
        match = re.search(r"(\d{1,2})\s+([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)\s+(20\d{2})", date)
        title = _text(event.select_one(".infobox_title"))
        place = _text(event.select_one(".infobox_loc"))
        link = event.select_one(".einf[href]") or event.select_one(".btn_kup[href]")
        month = _event_month(match.group(2)) if match else None
        if not match or not title or not place or "warszawa" not in _event_fold(place) or not link or not month:
            continue
        at = _event_at(match.group(1), month, fetched_at, "", match.group(3))
        if at:
            items.append({"title": title, "url": _event_url(link["href"], block_cfg), "at": at, "place": place})
    return items


def palladium(html, block_cfg, fetched_at):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for event in soup.select(".aktualnosc"):
        link = event.find("a", href=True)
        parts = [_text(part) for part in event.select(".post_date_inner > span")]
        title = _text(event.select_one(".post_title"))
        image = event.select_one("img[alt]")
        image_title = " ".join(image.get("alt", "").split()) if image else ""
        if title.endswith("...") and image_title:
            title = image_title
        if not link or len(parts) < 3 or not title:
            continue
        month = _event_month(parts[1])
        at = _event_at(parts[0], month, fetched_at, parts[2]) if month else None
        if not at:
            continue
        item = {"title": title, "url": _event_url(link["href"], block_cfg), "at": at}
        place = _text(event.select_one(".venue_logo"))
        if not place:
            logo = event.select_one(".venue_logo[alt]")
            place = " ".join(logo.get("alt", "").split()) if logo else ""
        if place:
            item["place"] = place
        items.append(item)
    return items


# Festivals, fairs and markets ------------------------------------------------

def _event_span(text, fetched_at):
    """'7 listopada 2026 - 8 listopada 2026', '22-23 listopada 2026', '28 lutego - 1 marca 2027', '16.01.2027',
    'sobota, 21 listopada 2026, 10:00' -> (start, end, time) with ISO dates, or None. Needs the year in the text."""
    text = " ".join((text or "").replace("\u2013", "-").split())
    match = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if match:
        day = _event_day(match.group(1), match.group(2), fetched_at, match.group(3))
        return (day, day, None) if day else None
    match = re.search(r"\b(\d{1,2})(?:\s+(\S+?))?(?:\s+(\d{4}))?\s*-\s*(\d{1,2})\s+(\S+)\s+(\d{4})", text)
    if match:
        d1, m1, y1, d2, m2, y2 = match.groups()
        end_month = _event_month(m2)
        start_month = _event_month(m1) if m1 else end_month
        if not start_month or not end_month:
            return None
        start = _event_day(d1, start_month, fetched_at, y1 or int(y2) - (start_month > end_month))
        end = _event_day(d2, end_month, fetched_at, y2)
        return (start, end, None) if start and end else None
    match = re.search(r"\b(\d{1,2})\s+(\S+)\s+(\d{4})(?:,\s*(\d{1,2}:\d{2}))?", text)
    month = _event_month(match.group(2)) if match else None
    day = month and _event_day(match.group(1), month, fetched_at, match.group(3))
    return (day, day, match.group(4)) if day else None


def _event_span_entry(title, url, span, **extra):
    """One dated day becomes a performance, a span of days a run."""
    start, end, time = span
    entry = {"title": title, "url": url, **{key: value for key, value in extra.items() if value}}
    if start == end:
        entry["at"] = f"{start}T{int(time.split(':')[0]):02d}:{time.split(':')[1]}" if time else start
    else:
        entry.update(start=start, end=end)
    return entry


def pik(html, block_cfg, fetched_at):
    """PIK Warszawa category pages (festiwal, jarmark, targi): posts with the event date in span.data."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for post in soup.select(".base-box.blog-post"):
        link = post.select_one(".bp-head h2 a[href]")
        span = _event_span(_text(post.select_one("span.data")), fetched_at)
        if not link or not span:
            continue
        summary = re.sub(r"\s*(Czytaj dalej|KUP BILET)\s*", " ", _text(post.select_one(".bp-details"))).strip()
        free = any("za-darmo" in a.get("href", "") for a in post.select(".mom-post-meta a"))
        title = re.sub(r"\s+[–-]\s+Bilety$", "", _text(link))
        items.append(_event_span_entry(title, _event_url(link["href"], block_cfg), span,
                                       summary=_event_summary(summary), tag="Za darmo" if free else None))
    return items


def drink_festivals(html, block_cfg, fetched_at):
    """facetpo40.pl's calendar of wine / whisky / beer festivals (Warsaw rows only), and the next edition
    announced on warszawskifestiwalpiwa.pl: the block fetches both pages and this parser reads either."""
    soup = BeautifulSoup(html, "html.parser")
    if "warszawskifestiwalpiwa.pl" in block_cfg["url"]:
        meta = soup.find("meta", attrs={"name": "description"})
        # "23. Warszawski Festiwal Piwa 11, 12 i 13 marca 2027 r. stadion Legii. ..."
        match = re.match(r"\s*(?:\d+\.\s*)?(.*?Festiwal Piwa)\s+([\d ,i]+?)\s+(\S+)\s+(\d{4})", meta.get("content", "") if meta else "")
        month = _event_month(match.group(3)) if match else None
        days = re.findall(r"\d+", match.group(2)) if month else []
        if not days:
            return []
        span = (_event_day(days[0], month, fetched_at, match.group(4)), _event_day(days[-1], month, fetched_at, match.group(4)), None)
        # Titled without the edition number, so it merges with the same festival's row in the facetpo40 calendar.
        return [_event_span_entry(match.group(1), block_cfg["url"], span, place="Stadion Legii")] if all(span[:2]) else []
    items = []
    for heading in soup.find_all("h2"):
        where, summary, url = None, "", None
        for node in heading.find_next_siblings():
            if node.name == "h2":
                break
            text = _text(node).replace("\u2013", "-")
            if where is None and " - " in text:
                where = text
            elif node.name == "ul":
                link = next((a for a in node.find_all("a", href=True) if "strona" in _text(a).lower()), None)
                url = url or (link["href"] if link else None)
            elif where is not None and not summary:
                summary = text
        if not where or not where.lower().startswith("warszaw"):
            continue
        span = _event_span(where.split(" - ", 1)[1], fetched_at)
        if span:
            items.append(_event_span_entry(_text(heading), url or block_cfg["url"], span, summary=_event_summary(summary)))
    return items
