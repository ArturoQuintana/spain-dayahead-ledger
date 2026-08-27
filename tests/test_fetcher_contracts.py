"""Contract tests for the four market fetchers' fetch_hourly ORCHESTRATION —
the layer the parser unit-tests don't reach: chunking, weekly-bucket selection,
the MIS listing parse + zip download, and the ENTSO-E UTC-window request.

Each test injects a REAL recorded response (tests/fixtures/, captured
2026-08-20/27) through the fetcher's `_open` seam and pins the exact hourly
dict. These are regression + schema-documentation contracts: if an upstream
provider's real shape (as recorded) stops parsing, or a refactor breaks the
orchestration, the build fails. (Live upstream drift is a separate concern —
that needs a scheduled smoke test, not a fixture.)
"""
import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from esios_paper import fetch, fetch_ercot, fetch_entsoe, fetch_smard

FIX = Path(__file__).resolve().parent / "fixtures"


class _Resp:
    def __init__(self, data: bytes):
        self._data = data
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def router(mapping: dict[str, bytes], calls: list):
    """A urlopen seam that returns recorded bytes by URL-substring match and
    records every URL it was asked for (so tests can assert what was fetched)."""
    def _open(url, timeout=None):
        calls.append(url)
        for needle, data in mapping.items():
            if needle in url:
                return _Resp(data)
        raise AssertionError(f"unexpected fetch: {url}")
    return _open


# ---- Spain (apidatos) --------------------------------------------------------

def test_es_apidatos_hourly_means_from_quarter_hour_values():
    raw = (FIX / "apidatos_es_2026-08-20.json").read_bytes()
    calls = []
    out = fetch.fetch_hourly(date(2026, 8, 20), date(2026, 8, 20),
                             _open=router({"apidatos.ree.es": raw}, calls))
    assert len(out) == 24
    assert out["2026-08-20T00"] == 194.59      # mean of the hour's 4 quarters
    assert out["2026-08-20T12"] == 50.41
    assert out["2026-08-20T23"] == 173.01
    assert len(calls) == 1                       # single chunk for one day


def test_es_chunks_ranges_over_28_days():
    raw = (FIX / "apidatos_es_2026-08-20.json").read_bytes()
    calls = []
    fetch.fetch_hourly(date(2026, 8, 20), date(2026, 9, 25),   # 37 days
                       _open=router({"apidatos.ree.es": raw}, calls))
    assert len(calls) == 2                       # 28-day chunk boundary
    calls.clear()
    fetch.fetch_hourly(date(2026, 8, 20), date(2026, 9, 10),   # 22 days
                       _open=router({"apidatos.ree.es": raw}, calls))
    assert len(calls) == 1


# ---- Germany (SMARD) ---------------------------------------------------------

def test_de_smard_selects_overlapping_bucket_only():
    index = (FIX / "smard_index_hour.json").read_bytes()
    bucket = (FIX / "smard_4169_DE_hour_1786917600000.json").read_bytes()
    calls = []
    out = fetch_smard.fetch_hourly(
        date(2026, 8, 20), date(2026, 8, 20),
        _open=router({"index_hour": index, "hour_1786917600000": bucket}, calls))
    assert len(out) == 24
    assert out["2026-08-20T00"] == 172.71
    assert out["2026-08-20T12"] == 83.63
    # index + exactly ONE weekly bucket (the one covering the day)
    series_calls = [c for c in calls if "4169_DE_hour_" in c]
    assert len(series_calls) == 1


# ---- Portugal / Italy (ENTSO-E A44) ------------------------------------------

def test_pt_entsoe_a44_aggregates_quarter_hours(monkeypatch):
    monkeypatch.setenv("ENTSOE_TOKEN", "test-token")   # _open is mocked anyway
    xml = (FIX / "entsoe_a44_pt_2026-08-20.xml").read_bytes()
    calls = []
    fetch_pt = fetch_entsoe.make_fetch(fetch_entsoe.PT, fetch_entsoe.LISBON,
                                       _open=router({"web-api.tp.entsoe.eu": xml}, calls))
    out = fetch_pt(date(2026, 8, 20), date(2026, 8, 20))
    assert len(out) == 24
    assert out["2026-08-20T00"] == 182.11
    assert out["2026-08-20T12"] == 110.11
    assert out["2026-08-20T23"] == 196.59
    assert "documentType=A44" in calls[0] and "securityToken=test-token" in calls[0]


# ---- ERCOT (MIS listing -> zip -> CSV) ---------------------------------------

def _ercot_zip() -> bytes:
    csv_text = (
        "DeliveryDate,HourEnding,SettlementPoint,SettlementPointPrice\n"
        "08/27/2026,01:00,HB_NORTH,42.10\n"
        "08/27/2026,02:00,HB_NORTH,38.55\n"
        "08/27/2026,01:00,HB_HOUSTON,44.00\n"
        "08/27/2026,24:00,HB_NORTH,50.25\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cdr.00012331.DAMSPNP4190_csv.csv", csv_text)
    return buf.getvalue()


def test_ercot_listing_parse_download_unzip_pipeline():
    listing = (FIX / "ercot_listing_12331.html").read_bytes()
    calls = []
    fetch_north = fetch_ercot.make_fetch(
        "HB_NORTH",
        _open=router({"GetReports.do": listing, "doclookupId=": _ercot_zip()}, calls))
    out = fetch_north(date(2026, 8, 27), date(2026, 8, 27))
    # HourEnding 01:00/02:00/24:00 -> local hours 0/1/23, HB_NORTH only
    assert out == {"2026-08-27T00": 42.10, "2026-08-27T01": 38.55,
                   "2026-08-27T23": 50.25}
    # listing fetched once; only 2026-08-27-delivery zips downloaded (not all 31)
    assert sum(1 for c in calls if "GetReports.do" in c) == 1
    downloads = sum(1 for c in calls if "doclookupId=" in c)
    assert 1 <= downloads <= 3      # posting revisions of the same delivery day
