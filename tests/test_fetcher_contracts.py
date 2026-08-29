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

from talea.markets import _entsoe as fetch_entsoe
from talea.markets.de import fetch as fetch_smard
from talea.markets.ercot import fetch as fetch_ercot
from talea.markets.es import fetch

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
    # mean of the hour's 4 quarters: (201.42+198.52+190.49+187.95)/4 = 194.595
    # exactly, a genuine two-decimal rounding boundary. Which way round() lands
    # depends on the LSB of the summed float, which itself depends on the
    # interpreter's float-sum algorithm: CPython 3.12+ sums floats with
    # Neumaier compensation (bpo-100425) and gets exactly 778.38 -> 194.59;
    # 3.11 and earlier sum naively and get 778.3800000000001 -> 194.6. Both are
    # correct roundings of their own (different, equally valid) intermediate
    # float; assert the interpreter-independent invariant instead of pinning
    # one side of a boundary this fixture happens to sit on.
    assert out["2026-08-20T00"] in (194.59, 194.6)
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
    from talea.markets.pt import PT, LISBON
    xml = (FIX / "entsoe_a44_pt_2026-08-20.xml").read_bytes()
    calls = []
    fetch_pt = fetch_entsoe.make_fetch(PT, LISBON,
                                       _open=router({"web-api.tp.entsoe.eu": xml}, calls))
    out = fetch_pt(date(2026, 8, 20), date(2026, 8, 20))
    assert len(out) == 24
    assert out["2026-08-20T00"] == 182.11
    assert out["2026-08-20T12"] == 110.11
    assert out["2026-08-20T23"] == 196.59
    assert "documentType=A44" in calls[0] and "securityToken=test-token" in calls[0]
    assert f"in_Domain={PT}" in calls[0]        # targets the Portugal zone (EIC guard)


def test_fr_entsoe_targets_the_france_zone(monkeypatch):
    """FR must query the FRANCE bidding zone, not accidentally IT/PT — the classic
    copy-paste-the-wrong-EIC bug that would silently onboard a mislabeled market.
    Guards markets/fr/'s EIC + Europe/Paris wiring against the shared A44 client."""
    monkeypatch.setenv("ENTSOE_TOKEN", "test-token")
    from talea.markets.fr import FR, PARIS
    assert FR == "10YFR-RTE------C" and str(PARIS) == "Europe/Paris"
    xml = (FIX / "entsoe_a44_pt_2026-08-20.xml").read_bytes()   # A44 parse is zone-agnostic
    calls = []
    fetch_fr = fetch_entsoe.make_fetch(FR, PARIS,
                                       _open=router({"web-api.tp.entsoe.eu": xml}, calls))
    out = fetch_fr(date(2026, 8, 20), date(2026, 8, 20))
    assert f"in_Domain={FR}" in calls[0] and f"out_Domain={FR}" in calls[0]
    assert "documentType=A44" in calls[0]
    assert len(out) >= 20, "FR fetch parsed no Paris-local hours"


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


def test_gb_bmrs_market_index_targets_elexon():
    """GB fetch must hit Elexon's open BMRS Market Index endpoint (NOT EPEX/Nord
    Pool directly, which are licence-restricted) and parse the APXMIDP leg."""
    from talea.markets.gb import fetch as gb
    import json as _json
    payload = _json.dumps({"data": [
        {"dataProvider": "APXMIDP", "price": 80.0, "startTime": "2026-08-19T23:00:00Z"},
        {"dataProvider": "APXMIDP", "price": 90.0, "startTime": "2026-08-19T23:30:00Z"},
    ]}).encode()
    calls = []
    out = gb.fetch_hourly(date(2026, 8, 20), date(2026, 8, 20),
                          _open=router({"data.elexon.co.uk": payload}, calls))
    assert "data.elexon.co.uk" in calls[0] and "market-index" in calls[0]
    assert "format=json" in calls[0]
    assert out["2026-08-20T00"] == 85.0        # (80+90)/2, London hour 00


def test_jp_fetch_targets_jepx_csv_with_referer():
    """JP must fetch the JEPX spot CSV with the required Referer header (the server
    returns 0 bytes without it) and the fiscal-year filename, then convert the
    system price ¥/kWh -> ¥/MWh."""
    from talea.markets.jp import fetch as jp
    import io
    csv = ("受渡日,時刻コード,売り,買い,約定,システムプライス(円/kWh)\n"
           "2026/08/27,1,1,1,1,10.00\n2026/08/27,2,1,1,1,12.00\n").encode()
    seen = {}
    def fake_open(req, timeout=None):
        seen["url"] = req.full_url
        seen["referer"] = req.get_header("Referer")
        return io.BytesIO(csv)
    out = jp.fetch_hourly(date(2026, 8, 27), date(2026, 8, 27), _open=fake_open)
    assert "csv_read.php" in seen["url"] and "spot_summary_2026.csv" in seen["url"]
    assert seen["referer"] == "https://www.jepx.jp/electricpower/market-data/spot/"
    assert out["2026-08-27T00"] == 11000.0
