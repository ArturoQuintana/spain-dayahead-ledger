"""Compat shim — the SMARD (DE) client moved to `markets/de/fetch.py` in Phase 2
(2026-08-28). Re-exported here so existing importers (`from esios_paper import
fetch_smard`) keep working; new code should import from
`esios_paper.markets.de.fetch`.
"""
from esios_paper.markets.de.fetch import (  # noqa: F401
    ATTRIBUTION, BERLIN, INDEX_URL, SERIES_URL, fetch_hourly, parse_series)

__all__ = ["ATTRIBUTION", "BERLIN", "INDEX_URL", "SERIES_URL",
           "fetch_hourly", "parse_series"]
