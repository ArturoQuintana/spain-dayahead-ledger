"""Compat shim — the ERCOT MIS client moved to `markets/ercot/fetch.py` in Phase 2
(2026-08-28). Re-exported here so existing importers (`from esios_paper import
fetch_ercot`, the ercot.yml workflow) keep working; new code should import from
`esios_paper.markets.ercot.fetch`.
"""
from esios_paper.markets.ercot.fetch import (  # noqa: F401
    DISCLAIMER, DOWNLOAD_URL, LISTING_URL, fetch_hourly, make_fetch, parse_dam_csv)

__all__ = ["DISCLAIMER", "DOWNLOAD_URL", "LISTING_URL",
           "fetch_hourly", "make_fetch", "parse_dam_csv"]
