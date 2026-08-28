"""SMARD.de client for German (DE-LU) day-ahead spot prices. Stdlib-only.

Data source: Bundesnetzagentur | SMARD.de, licensed CC BY 4.0 (verified
2026-08-22). SMARD serves the day-ahead wholesale price (filter 4169,
region DE-LU, hourly resolution) as weekly buckets: an index of bucket-start
epochs, then one file per bucket holding [epoch_ms_UTC, price|null] pairs.
Epochs are UTC; we key by Europe/Berlin local clock hour ("YYYY-MM-DDTHH"),
the same market-local frame the rest of the project uses.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
INDEX_URL = "https://www.smard.de/app/chart_data/4169/DE/index_hour.json"
SERIES_URL = "https://www.smard.de/app/chart_data/4169/DE/4169_DE_hour_{}.json"
ATTRIBUTION = "Bundesnetzagentur | SMARD.de (CC BY 4.0)"


def parse_series(series: list, start: date, end: date) -> dict[str, float]:
    """[[epoch_ms_UTC, price|null], ...] -> {"YYYY-MM-DDTHH": price} for the
    Europe/Berlin local days in [start, end]. Nulls (unpublished/future
    hours) are dropped. Pure — unit-tested against a recorded fixture.

    DST note: keyed by local clock hour, so the autumn fall-back day's
    repeated 02:00 collapses to one key (a documented 1-hour/year artifact,
    identical to the Spanish frame)."""
    out: dict[str, float] = {}
    for epoch, val in series:
        if val is None:
            continue
        local = datetime.fromtimestamp(epoch / 1000, tz=timezone.utc).astimezone(BERLIN)
        if start <= local.date() <= end:
            out[local.strftime("%Y-%m-%dT%H")] = round(float(val), 2)
    return out


def fetch_hourly(start: date, end: date, *, _open=urllib.request.urlopen) -> dict[str, float]:
    """Hourly DE-LU day-ahead prices for [start, end] inclusive, keyed by
    Berlin local hour. Fetches only the weekly buckets overlapping the range.
    Raises on network/HTTP errors (the caller decides if stale data is OK)."""
    with _open(INDEX_URL, timeout=60) as r:
        buckets = json.load(r)["timestamps"]
    out: dict[str, float] = {}
    for b in buckets:
        b_start = datetime.fromtimestamp(b / 1000, tz=timezone.utc).astimezone(BERLIN).date()
        b_end = date.fromordinal(b_start.toordinal() + 7)
        if b_end < start or b_start > end:
            continue
        with _open(SERIES_URL.format(b), timeout=60) as r:
            series = json.load(r)["series"]
        out.update(parse_series(series, start, end))
    return out
