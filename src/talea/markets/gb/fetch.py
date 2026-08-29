"""Great Britain (GB) day-ahead price client — Elexon BMRS "Market Index Data".
Stdlib-only.

Source & license: Elexon's Insights Solution / BMRS. Elexon publishes the
day-ahead Market Index Price as the statutory Balancing Mechanism Reporting Agent
and states the Insights data is "open and available for anyone to access, modify
and distribute" — so GB is PUBLIC/redistributable, same tier as ES (apidatos) and
DE (SMARD). We fetch via Elexon, NOT directly from EPEX SPOT / Nord Pool, whose own
data channels are licence-restricted.

Endpoint (no auth): data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index
Records are HALF-HOURLY settlement periods, each tagged `dataProvider`:
`APXMIDP` (EPEX leg) and `N2EXMIDP` (Nord Pool leg). As of 2026-08 the N2EX leg is
uniformly 0.00 (dead feed), so we use `APXMIDP` ONLY — averaging the legs would
silently corrupt the price. The two half-hours of each Europe/London local hour are
aggregated to an hourly mean, keyed "YYYY-MM-DDTHH" local (same frame as every other
market). Prices are £/MWh (GBP).

NOTE (2026-08-28): built to Elexon's documented schema but NOT yet pinned against a
recorded response — validate live before committing receipts (the parser tolerates
either a UTC `startTime` field or `settlementDate`+`settlementPeriod`).
"""
from __future__ import annotations

import json
import statistics
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
API = "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index"
PROVIDER = "APXMIDP"        # the populated leg; N2EXMIDP is all-zero (2026-08)
ATTRIBUTION = "Elexon BMRS Market Index Data (Insights Solution, open data)"


def parse_market_index(payload, start: date, end: date) -> dict[str, float]:
    """BMRS market-index JSON -> {"YYYY-MM-DDTHH": price} for Europe/London local
    days in [start, end], APXMIDP leg only, half-hours aggregated to the hourly
    mean. Pure. DST: keyed by London clock hour, so the autumn repeated hour
    collapses to one key (the shared 1-hour/year artifact)."""
    records = payload.get("data", payload) if isinstance(payload, dict) else payload
    hour_vals: dict[str, list[float]] = {}
    for rec in records:
        if rec.get("dataProvider") != PROVIDER:
            continue
        price = rec.get("price")
        if price is None:
            continue
        ts = rec.get("startTime") or rec.get("startTimeGmt") or rec.get("publishTime")
        if ts:
            local = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LONDON)
        else:                                   # fall back to settlementDate + period
            d = date.fromisoformat(rec["settlementDate"])
            p = int(rec["settlementPeriod"])    # period 1 = 00:00–00:30 local
            local = datetime(d.year, d.month, d.day, tzinfo=LONDON) + timedelta(minutes=(p - 1) * 30)
        if start <= local.date() <= end:
            hour_vals.setdefault(local.strftime("%Y-%m-%dT%H"), []).append(float(price))
    return {k: round(statistics.fmean(v), 2) for k, v in hour_vals.items()}


# Elexon caps the market-index from->to range at 7 days INCLUSIVE (HTTP 400
# "The date range between From and To inclusive must not exceed 7 days"). A market
# with no seed data fetches from loop.py's default start (~7 months back), so a
# single request over-runs the cap. We CHUNK the window into <=7-day requests and
# merge; a normal daily tick is one chunk. (Discovered 2026-08-29: GB 400'd on
# EVERY scheduled tick because its first fetch asked for the whole Jan->Aug
# backfill in one call — it only ever "worked" in a hand-run 2-day smoke test.)
_MAX_CHUNK_DAYS = 6   # 6 inclusive local days -> ~148h span, safely under 7 days


def _fetch_window(frm_date: date, to_date: date, _open) -> object:
    frm = datetime(frm_date.year, frm_date.month, frm_date.day, tzinfo=LONDON) - timedelta(hours=2)
    to = datetime(to_date.year, to_date.month, to_date.day, tzinfo=LONDON) + timedelta(days=1, hours=2)
    url = (f"{API}?from={frm.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
           f"&to={to.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}&format=json")
    with _open(url, timeout=60) as r:
        return json.load(r)


def fetch_hourly(start: date, end: date, *, _open=urllib.request.urlopen) -> dict[str, float]:
    """Hourly GB day-ahead (Market Index, APXMIDP) prices for [start, end]
    inclusive, keyed by Europe/London local hour. Splits the window into
    <=7-day chunks (Elexon's hard cap) and merges. Raises on network/HTTP errors
    (the caller decides if stale is OK)."""
    out: dict[str, float] = {}
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=_MAX_CHUNK_DAYS - 1), end)
        payload = _fetch_window(cur, chunk_end, _open)
        out.update(parse_market_index(payload, cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out
