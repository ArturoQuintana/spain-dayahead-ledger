"""ERCOT client for Texas day-ahead (DAM) settlement point prices. Stdlib-only.

Data source: ERCOT public MIS, report NP4-190 (DAM Settlement Point Prices,
classified Public; redistribution permitted under ERCOT Website User
Agreement s.5 raw-data carve-out, verified 2026-08-22). The public listing
(reportTypeId=12331) links one CSV zip per posting day; the file posted on
day D contains the full 24-hour delivery day D+1 for every settlement point.
We keep one hub (default HB_NORTH) and key by delivery-day local clock hour
("YYYY-MM-DDTHH", America/Chicago). USD/MWh.

Do NOT use the Data Portal API (3-downloads/12-months cap) — the MIS listing
is uncapped. Do not use ERCOT trademarks/logos in published output.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request
import zipfile
from datetime import date, timedelta

LISTING_URL = "https://www.ercot.com/misapp/GetReports.do?reportTypeId=12331"
DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload?mimic_duns=000000000&doclookupId={}"
DISCLAIMER = ("Source: ERCOT public data (NP4-190, DAM Settlement Point "
              "Prices); provided as-is; not affiliated with or endorsed by ERCOT")
# pairs each CSV zip's filename with its download doclookupId, in listing order
_ROW_RE = re.compile(r"(cdr\.[^<]*?DAMSPNP4190_csv\.zip)</td>.*?doclookupId=(\d+)",
                     re.DOTALL)
_POSTDATE_RE = re.compile(r"\.(\d{8})\.\d+\.DAMSPNP4190_csv\.zip")


def parse_dam_csv(text: str, hub: str, start: date, end: date) -> dict[str, float]:
    """ERCOT DAM SPP CSV -> {"YYYY-MM-DDTHH": price} for `hub` on delivery
    days in [start, end]. HourEnding "01:00".."24:00" maps to hour 0..23.
    Pure — unit-tested against a recorded fixture.

    DST note: on the autumn 25-hour day ERCOT emits a duplicate HourEnding
    with DSTFlag=Y; keyed by local clock hour these collapse to one key (the
    same documented 1-hour/year artifact as the other markets). First row
    wins (deterministic)."""
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row["SettlementPoint"].strip() != hub:
            continue
        mm, dd, yyyy = row["DeliveryDate"].strip().split("/")
        d = date(int(yyyy), int(mm), int(dd))
        if not (start <= d <= end):
            continue
        hour = int(row["HourEnding"].strip()[:2]) - 1
        key = f"{d.isoformat()}T{hour:02d}"
        if key not in out:                       # first (non-DST-repeat) wins
            out[key] = round(float(row["SettlementPointPrice"].strip()), 2)
    return out


def make_fetch(hub: str = "HB_NORTH", *, _open=urllib.request.urlopen):
    """Return a fetch_hourly(start, end) closure for one ERCOT hub, matching
    the Market.fetch signature. Downloads only the CSV files whose delivery
    day falls in [start, end] (posting day D -> delivery D+1)."""
    def fetch_hourly(start: date, end: date) -> dict[str, float]:
        with _open(LISTING_URL, timeout=60) as r:
            html = r.read().decode("utf-8", "replace")
        out: dict[str, float] = {}
        for fname, doclookup in _ROW_RE.findall(html):
            m = _POSTDATE_RE.search(fname)
            if not m:
                continue
            posted = date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8]))
            delivery = posted + timedelta(days=1)
            if not (start <= delivery <= end):
                continue
            with _open(DOWNLOAD_URL.format(doclookup), timeout=60) as r:
                blob = r.read()
            zf = zipfile.ZipFile(io.BytesIO(blob))
            text = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
            out.update(parse_dam_csv(text, hub, start, end))
        return out
    return fetch_hourly


fetch_hourly = make_fetch("HB_NORTH")
