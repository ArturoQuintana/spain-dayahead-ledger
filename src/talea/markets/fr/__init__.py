"""France (FR) — EPEX SPOT day-ahead via ENTSO-E. DERIVED-METRICS-ONLY (prices
never republished), private — the same ENTSO-E source and license basis as IT/PT.
SDAC-coupled, gate 12:00 CET, Europe/Paris.

STRUCTURE PRINCIPLE (why there is no `markets/fr/fetch.py`): a `fetch.py` exists to
house a market's DEDICATED fetch LOGIC — DE owns the SMARD client, ERCOT the MIS
pipeline. FR owns none: it uses the SHARED ENTSO-E A44 library
(`markets/_entsoe.py`), so its fetch is a one-line zone/tz BINDING
(config, not logic) and lives inline with the Market config below. IT and PT are
INDEPENDENT markets with the same ENTSO-E behavior and bind the shared library the
same way; the Phase-2 extraction to `markets/_entsoe.py` decouples all three from
today's shared-module entanglement (plan defect #3) without adding ceremony files.
FR completes EU price-regime coverage (French central-west) and is the flagship of
the SDAC FR/BE/NL cluster (docs/market-expansion-shortlist-2026-08.md).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from ..base import Market, Presentation
from .._entsoe import make_fetch          # the shared ENTSO-E A44 library

PARIS = ZoneInfo("Europe/Paris")
FR = "10YFR-RTE------C"        # ENTSO-E EIC for the France bidding zone (validated 2026-08-28)

MARKET = Market.make("fr", PARIS, make_fetch(FR, PARIS),
                     deadline_hour=12, currency="EUR",
                     presentation=Presentation(
                         title="French (FR) day-ahead battery arbitrage",
                         tab_name="France", tz_label="Paris",
                         source="ENTSO-E (private use; prices not redistributed)"))
