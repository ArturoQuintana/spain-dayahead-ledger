"""Tests for the DE (SMARD) and ERCOT day-ahead fetchers. The pure parsers
are pinned against recorded fixtures of the real API/CSV shapes (captured
2026-08-22); the thin network wrappers are smoke-tested live out of band, not
here (CI stays network-free)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from talea.markets.de import fetch as fetch_smard
from talea.markets.ercot import fetch as fetch_ercot

ROME = ZoneInfo("Europe/Rome")   # sample tz for the library parse_a44 tests
LISBON = ZoneInfo("Europe/Lisbon")

FIX = Path(__file__).parent / "fixtures"


def test_smard_parse_series_maps_utc_epochs_to_berlin_and_drops_nulls():
    series = json.loads((FIX / "smard_series.json").read_text())["series"]
    # fixture: 5 real hourly points from 2026-08-16 22:00 UTC on, + 1 null
    out = fetch_smard.parse_series(series, date(2026, 8, 16), date(2026, 8, 17))
    # 1786917600000 = 2026-08-16 22:00 UTC = 2026-08-17 00:00 Berlin (CEST)
    assert out["2026-08-17T00"] == 192.13
    assert out["2026-08-17T01"] == 178.81
    # the null point is dropped, not stored as None
    assert all(v is not None for v in out.values())
    # range filter excludes the 08-16-local nothing / keeps only in-range
    assert all(k.startswith("2026-08-17") for k in out)


def test_smard_parse_series_respects_range():
    series = json.loads((FIX / "smard_series.json").read_text())["series"]
    assert fetch_smard.parse_series(series, date(2030, 1, 1), date(2030, 1, 2)) == {}


def test_ercot_parse_dam_csv_hub_hour_and_price():
    text = (FIX / "ercot_dam.csv").read_text()
    out = fetch_ercot.parse_dam_csv(text, "HB_NORTH", date(2026, 8, 23), date(2026, 8, 23))
    # HourEnding 01:00 -> hour 0; leading-space price stripped
    assert out["2026-08-23T00"] == 30.98
    assert out["2026-08-23T01"] == 26.93
    # HB_HUBAVG rows must be excluded when hub=HB_NORTH
    assert all(v in (30.98, 26.93) for v in out.values())


def test_ercot_parse_dam_csv_other_hub_and_range():
    text = (FIX / "ercot_dam.csv").read_text()
    avg = fetch_ercot.parse_dam_csv(text, "HB_HUBAVG", date(2026, 8, 23), date(2026, 8, 23))
    assert avg["2026-08-23T00"] == 31.63
    # out-of-range delivery day -> empty
    assert fetch_ercot.parse_dam_csv(text, "HB_NORTH", date(2026, 1, 1),
                                     date(2026, 1, 2)) == {}


def test_entsoe_parse_a44_aggregates_quarter_hours_and_fills_gaps():
    from talea.markets import _entsoe as fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    out = fetch_entsoe.parse_a44(xml, ROME, date(2026, 8, 24), date(2026, 8, 24))
    # period start 22:00Z = 00:00 Rome (CEST +2); 8 quarter-hours = 2 local hours
    # hour 00: pos1=100, pos2=200, pos3 MISSING->200 (A03 fill-forward), pos4=400
    assert out["2026-08-24T00"] == 225.0     # (100+200+200+400)/4
    # hour 01: 10,20,30,40
    assert out["2026-08-24T01"] == 25.0
    assert set(out) == {"2026-08-24T00", "2026-08-24T01"}


def test_entsoe_parse_a44_range_filter():
    from talea.markets import _entsoe as fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    assert fetch_entsoe.parse_a44(xml, ROME, date(2030, 1, 1), date(2030, 1, 2)) == {}


def test_entsoe_parser_respects_timezone_for_pt_vs_it():
    from talea.markets import _entsoe as fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    # same UTC data, different zone -> different local-hour keys (PT=Lisbon is
    # one hour behind IT=Rome), proving the tz is actually threaded through.
    it = fetch_entsoe.parse_a44(xml, ROME, date(2026, 8, 23), date(2026, 8, 24))
    pt = fetch_entsoe.parse_a44(xml, LISBON, date(2026, 8, 23), date(2026, 8, 24))
    assert it != pt
    # (the PT EIC is now owned by markets/pt and asserted in its contract test)


def test_gb_market_index_apxmidp_only_hourly_mean():
    """GB (Elexon BMRS Market Index): half-hourly APXMIDP aggregated to the London
    hourly mean; the dead N2EXMIDP leg (all-zero, 2026-08) is excluded — averaging
    it in would corrupt the price."""
    from talea.markets.gb import fetch as gb
    payload = {"data": [
        # London BST = UTC+1: UTC 23:00/23:30 of 08-19 -> 00:00/00:30 London 08-20 (hour 00)
        {"dataProvider": "APXMIDP",  "price": 100.0, "startTime": "2026-08-19T23:00:00Z"},
        {"dataProvider": "APXMIDP",  "price": 120.0, "startTime": "2026-08-19T23:30:00Z"},
        {"dataProvider": "N2EXMIDP", "price": 0.0,   "startTime": "2026-08-19T23:00:00Z"},  # dead leg
        {"dataProvider": "APXMIDP",  "price": 50.0,  "startTime": "2026-08-20T00:00:00Z"},  # hour 01
        {"dataProvider": "APXMIDP",  "price": 60.0,  "startTime": "2026-08-20T00:30:00Z"},
    ]}
    out = gb.parse_market_index(payload, date(2026, 8, 20), date(2026, 8, 20))
    assert out["2026-08-20T00"] == 110.0    # (100+120)/2 — N2EX 0.0 excluded
    assert out["2026-08-20T01"] == 55.0     # (50+60)/2
    assert 0.0 not in out.values()


def test_jp_jepx_spot_system_price_hourly_and_unit_conversion():
    """JEPX spot: SYSTEM price (col 5), the two 30-min slots of each hour aggregated
    to the hourly mean, ¥/kWh -> ¥/MWh (×1000). Real CSV column shape; header + other
    days skipped by the numeric parse."""
    from talea.markets.jp import fetch as jp
    header = ("受渡日,時刻コード,売り入札量(kWh),買い入札量(kWh),約定総量(kWh),"
              "システムプライス(円/kWh),エリアプライス北海道(円/kWh)")
    csv = "\n".join([
        header,
        "2026/08/27,1,1,1,1,10.00,9.0",   # hour 00, slot 1
        "2026/08/27,2,1,1,1,12.00,9.0",   # hour 00, slot 2 -> (10+12)/2 * 1000
        "2026/08/27,3,1,1,1,20.00,9.0",   # hour 01, slot 3
        "2026/08/27,4,1,1,1,30.00,9.0",   # hour 01, slot 4 -> (20+30)/2 * 1000
        "2026/08/28,1,1,1,1,99.00,9.0",   # different day -> filtered out
    ])
    out = jp.parse_spot_summary(csv, date(2026, 8, 27), date(2026, 8, 27))
    assert out["2026-08-27T00"] == 11000.0    # system price only; ¥/kWh -> ¥/MWh
    assert out["2026-08-27T01"] == 25000.0
    assert set(out) == {"2026-08-27T00", "2026-08-27T01"}   # header + other day skipped


def test_jp_fiscal_year_boundary():
    from talea.markets.jp import fetch as jp
    assert jp.fiscal_year(date(2026, 4, 1)) == 2026     # April -> FY2026
    assert jp.fiscal_year(date(2026, 3, 31)) == 2025    # March -> prior FY
    assert jp.fiscal_year(date(2027, 1, 15)) == 2026    # Jan -> prior FY
