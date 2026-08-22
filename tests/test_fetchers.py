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
