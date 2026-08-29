"""Japan (JP) day-ahead spot price client — JEPX (Japan Electric Power Exchange)
spot market results. Stdlib-only.

Source & license: JEPX publishes its spot results as downloadable CSV; its
disclaimer permits use WITH ATTRIBUTION ("利用する場合は、出所を明示した上でご利用
下さい") and asserts no redistribution ban — an attribution-required open grant, so
JP is treated as REDISTRIBUTABLE/public-eligible (a confirming email to JEPX would
fully close the residual gap on the un-named licence).

The CSV is per Japanese FISCAL YEAR (April–March): `spot_summary_{FY}.csv`. A
delivery day in Jan–Mar of year Y lives in FY {Y-1}. The fetch REQUIRES a `Referer`
header (the server returns 0 bytes without it); no auth/key. Columns (UTF-8,
verified live): 受渡日 (date YYYY/MM/DD, col 0), 時刻コード (30-min slot 1–48,
col 1), システムプライス(円/kWh) (the SYSTEM/national price, col 5), then 9 area
prices. We use the SYSTEM price, aggregate the two 30-min slots of each Asia/Tokyo
hour to the hourly mean, and convert ¥/kWh → ¥/MWh (×1000) to match the other
markets' per-MWh convention. Japan has NO DST — 48 slots every day, clean mapping.
"""
from __future__ import annotations

import statistics
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")
API = "https://www.jepx.jp/js/csv_read.php"
REFERER = "https://www.jepx.jp/electricpower/market-data/spot/"
ATTRIBUTION = "JEPX spot market data (source indicated per JEPX terms of use)"
SYSTEM_PRICE_COL = 5        # システムプライス(円/kWh)


def fiscal_year(d: date) -> int:
    """Japanese fiscal year (April–March): a day in Jan–Mar belongs to the prior FY."""
    return d.year if d.month >= 4 else d.year - 1


def parse_spot_summary(text: str, start: date, end: date) -> dict[str, float]:
    """JEPX spot_summary CSV -> {"YYYY-MM-DDTHH": price ¥/MWh} for Asia/Tokyo days in
    [start, end]: the SYSTEM price, the two 30-min slots of each hour aggregated to
    the hourly mean, ¥/kWh converted to ¥/MWh. Pure. The header row and any blank/
    malformed line fail the numeric parse and are skipped."""
    hour_vals: dict[str, list[float]] = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) <= SYSTEM_PRICE_COL:
            continue
        try:
            d = datetime.strptime(parts[0].strip(), "%Y/%m/%d").date()
            slot = int(parts[1])
            price = float(parts[SYSTEM_PRICE_COL])
        except (ValueError, IndexError):
            continue
        if not (start <= d <= end):
            continue
        hour = (slot - 1) // 2          # slots 1,2->00; 3,4->01; …; 47,48->23
        hour_vals.setdefault(f"{d.isoformat()}T{hour:02d}", []).append(price * 1000.0)
    return {k: round(statistics.fmean(v), 2) for k, v in hour_vals.items()}


def fetch_hourly(start: date, end: date, *, _open=urllib.request.urlopen) -> dict[str, float]:
    """Hourly JP day-ahead (JEPX system) prices for [start, end] inclusive, keyed by
    Asia/Tokyo local hour, in ¥/MWh. Fetches the fiscal-year CSV(s) covering the
    range (Referer header required). Raises on network/HTTP errors."""
    text = ""
    for fy in sorted({fiscal_year(start), fiscal_year(end)}):
        url = f"{API}?dir=spot_summary&file=spot_summary_{fy}.csv"
        req = urllib.request.Request(url, headers={"Referer": REFERER})
        with _open(req, timeout=60) as r:
            text += r.read().decode("utf-8", "replace") + "\n"
    return parse_spot_summary(text, start, end)
