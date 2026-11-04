"""Write fx/data/rates.json: NBP Table A mid rates (PLN per 1 unit) for USD, EUR and CNY since 2019.

The home page draws the exchange-rate charts from this file. It refetches the whole history every
run (8 requests per currency), which keeps it simple and self-healing; NBP allows at most 367 days
per request, hence one request per calendar year.
Run by .github/workflows/fx.yml on weekdays after NBP publishes the day's table.
"""
import datetime as dt
import json
import pathlib
import urllib.request

CODES = ["USD", "EUR", "CNY"]
START_YEAR = 2019
OUT = pathlib.Path(__file__).resolve().parents[2] / "fx" / "data" / "rates.json"


def fetch(code, start, end):
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{code.lower()}/{start}/{end}/?format=json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [(x["effectiveDate"], x["mid"]) for x in json.load(r)["rates"]]


def main():
    today = dt.date.today()
    series = {}
    for code in CODES:
        rows = []
        for y in range(START_YEAR, today.year + 1):
            rows += fetch(code, dt.date(y, 1, 1), min(dt.date(y, 12, 31), today))
        series[code] = dict(rows)
    # Table A lists every currency on the same days; keep only days all three have, so one date list serves all.
    dates = sorted(set.intersection(*(set(s) for s in series.values())))
    out = {
        "source": "NBP Table A (mid rate, PLN per 1 unit)",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dates": dates,
        **{code: [series[code][d] for d in dates] for code in CODES},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(dates)} days, {dates[0]} to {dates[-1]}: " + ", ".join(f"{c} {out[c][-1]}" for c in CODES))


if __name__ == "__main__":
    main()
