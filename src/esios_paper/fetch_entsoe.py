"""ENTSO-E Transparency client for Italian (IT-SUD) day-ahead zonal prices.
Stdlib-only.

Used for Italy under the DERIVED-METRICS-ONLY model (decision 2026-08-22):
GME's own terms forbid republishing prices, and ENTSO-E's day-ahead prices
are not on its free-reuse list — so we FETCH privately (legitimate private
use) and never republish the raw series (the public mirror redacts `it`
prices; only P&L/capture/tau are ever published).

The A44 (day-ahead prices) document is a Publication_MarketDocument with one
TimeSeries per delivery day, each a Period of PT15M points (Italy is
quarter-hourly since the 2025 MTU switch), curveType A03 = variable block:
a missing position carries the previous point's price forward. Point
positions map to UTC times from the Period start; we aggregate the four
quarter-hours of each Europe/Rome local hour to an hourly mean, keyed
"YYYY-MM-DDTHH" local — the same hourly frame as the other markets.

Auth: a free ENTSO-E security token in ENTSOE_TOKEN (env or repo .env).
"""
from __future__ import annotations

import os
import statistics
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
IT_SUD = "10Y1001A1001A73I"      # ENTSO-E EIC for bidding zone IT-SUD
API = "https://web-api.tp.entsoe.eu/api"
ATTRIBUTION = "ENTSO-E Transparency Platform (private use; prices not redistributed)"


def _token() -> str:
    t = os.getenv("ENTSOE_TOKEN")
    if not t:
        envf = Path(__file__).resolve().parents[2] / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("ENTSOE_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not t:
        raise RuntimeError("ENTSOE_TOKEN not set (env or .env)")
    return t


def parse_a44(xml_text: str, start: date, end: date) -> dict[str, float]:
    """A44 XML -> {"YYYY-MM-DDTHH": price} for Europe/Rome local days in
    [start, end]. Quarter-hour points (curveType A03: gaps carry the previous
    price forward) are aggregated to the hourly mean. Pure — unit-tested
    against a synthetic fixture of the real structure.

    DST: keyed by Rome local clock hour, so the autumn repeated hour collapses
    to one key (the documented 1-hour/year artifact shared by every market)."""
    root = ET.fromstring(xml_text)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    hour_vals: dict[str, list[float]] = {}
    for series in root.findall(".//n:TimeSeries", ns):
        res_txt = series.find(".//n:resolution", ns).text        # e.g. PT15M
        step = int("".join(c for c in res_txt if c.isdigit()))   # minutes
        for period in series.findall("n:Period", ns):
            p_start = datetime.fromisoformat(
                period.find("n:timeInterval/n:start", ns).text.replace("Z", "+00:00"))
            p_end = datetime.fromisoformat(
                period.find("n:timeInterval/n:end", ns).text.replace("Z", "+00:00"))
            n = round((p_end - p_start).total_seconds() / 60 / step)
            present = {int(pt.find("n:position", ns).text):
                       float(pt.find("n:price.amount", ns).text)
                       for pt in period.findall("n:Point", ns)}
            last = None
            for pos in range(1, n + 1):
                last = present.get(pos, last)          # A03 fill-forward
                if last is None:
                    continue
                t_utc = p_start + timedelta(minutes=(pos - 1) * step)
                local = t_utc.astimezone(ROME)
                if start <= local.date() <= end:
                    hour_vals.setdefault(local.strftime("%Y-%m-%dT%H"), []).append(last)
    return {k: round(statistics.fmean(v), 2) for k, v in hour_vals.items()}


def fetch_hourly(start: date, end: date, *, _open=urllib.request.urlopen) -> dict[str, float]:
    """Hourly IT-SUD day-ahead prices for [start, end] inclusive, Rome-local.
    Requests a UTC window covering the local days (Italian delivery day D runs
    ~22:00Z(D-1)..22:00Z(D)); the parser filters to local dates. Raises on
    network/HTTP errors."""
    ps = (datetime(start.year, start.month, start.day, tzinfo=ROME) - timedelta(hours=2))
    pe = (datetime(end.year, end.month, end.day, tzinfo=ROME) + timedelta(days=1))
    url = (f"{API}?securityToken={_token()}&documentType=A44"
           f"&in_Domain={IT_SUD}&out_Domain={IT_SUD}"
           f"&periodStart={ps.astimezone(timezone.utc):%Y%m%d%H%M}"
           f"&periodEnd={pe.astimezone(timezone.utc):%Y%m%d%H%M}")
    with _open(url, timeout=60) as r:
        xml_text = r.read().decode("utf-8", "replace")
    return parse_a44(xml_text, start, end)
