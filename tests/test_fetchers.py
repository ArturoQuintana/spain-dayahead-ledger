"""Tests for the DE (SMARD) and ERCOT day-ahead fetchers. The pure parsers
are pinned against recorded fixtures of the real API/CSV shapes (captured
2026-08-22); the thin network wrappers are smoke-tested live out of band, not
here (CI stays network-free)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from esios_paper import fetch_ercot, fetch_smard

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
    from esios_paper import fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    out = fetch_entsoe.parse_a44(xml, fetch_entsoe.ROME, date(2026, 8, 24), date(2026, 8, 24))
    # period start 22:00Z = 00:00 Rome (CEST +2); 8 quarter-hours = 2 local hours
    # hour 00: pos1=100, pos2=200, pos3 MISSING->200 (A03 fill-forward), pos4=400
    assert out["2026-08-24T00"] == 225.0     # (100+200+200+400)/4
    # hour 01: 10,20,30,40
    assert out["2026-08-24T01"] == 25.0
    assert set(out) == {"2026-08-24T00", "2026-08-24T01"}


def test_entsoe_parse_a44_range_filter():
    from esios_paper import fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    assert fetch_entsoe.parse_a44(xml, fetch_entsoe.ROME, date(2030, 1, 1), date(2030, 1, 2)) == {}


def test_entsoe_parser_respects_timezone_for_pt_vs_it():
    from esios_paper import fetch_entsoe
    xml = (FIX / "entsoe_a44.xml").read_text()
    # same UTC data, different zone -> different local-hour keys (PT=Lisbon is
    # one hour behind IT=Rome), proving the tz is actually threaded through.
    it = fetch_entsoe.parse_a44(xml, fetch_entsoe.ROME, date(2026, 8, 23), date(2026, 8, 24))
    pt = fetch_entsoe.parse_a44(xml, fetch_entsoe.LISBON, date(2026, 8, 23), date(2026, 8, 24))
    assert it != pt
    assert fetch_entsoe.PT == "10YPT-REN------W"
