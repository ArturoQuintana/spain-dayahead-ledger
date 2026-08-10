"""REE public API client for Spanish day-ahead spot prices. Stdlib-only.

The 'Precio mercado spot' series is quarter-hourly since the 15-minute MTU
change; we aggregate to hourly means keyed "YYYY-MM-DDTHH" in Europe/Madrid
local time (the API's native frame; the whole project stays in that frame).
The API rejects ranges over ~1 month, so requests are chunked to <=28 days.
"""
from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

API = ("https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
       "?start_date={s}T00:00&end_date={e}T23:59&time_trunc=hour")
CHUNK_DAYS = 28


def fetch_hourly(start: date, end: date) -> dict[str, float]:
    """Hourly mean spot prices for [start, end] (inclusive), {ts_hour: price}.
    Days the market hasn't published yet are simply absent from the result.
    Raises on network/HTTP errors — the caller decides whether stale data is
    acceptable for its purpose (settlement can wait; commitment must not guess).
    """
    out: dict[str, list[float]] = defaultdict(list)
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        url = API.format(s=cur.isoformat(), e=chunk_end.isoformat())
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.load(r)
        spot = next((i for i in data.get("included", [])
                     if "spot" in i["attributes"]["title"].lower()), None)
        if spot is not None:
            for v in spot["attributes"]["values"]:
                out[v["datetime"][:13]].append(float(v["value"]))
        cur = chunk_end + timedelta(days=1)
    return {k: round(sum(v) / len(v), 2) for k, v in sorted(out.items())}
