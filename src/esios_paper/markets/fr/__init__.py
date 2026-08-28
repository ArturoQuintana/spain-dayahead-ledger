"""France (FR) — EPEX SPOT day-ahead via ENTSO-E. DERIVED-METRICS-ONLY (prices
never republished), private — the SAME ENTSO-E source and license basis as IT/PT,
so no new redistribution terms are needed. SDAC-coupled, gate 12:00 CET,
Europe/Paris.

FIRST market built as a vertical `markets/<slug>/` module on the Phase-1 contract
(2026-08-28): this module owns only France's specifics — its ENTSO-E bidding-zone
EIC, timezone, and presentation — while the shared A44 client (`fetch_entsoe`)
stays a library. The incumbents migrate into this shape in Phase 2. FR completes
EU price-regime coverage (French nuclear/central-west); it is the flagship of the
SDAC-coupled FR/BE/NL cluster (docs/market-expansion-shortlist-2026-08.md).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from esios_paper import fetch_entsoe
from esios_paper.markets.base import Market, Presentation

PARIS = ZoneInfo("Europe/Paris")
FR = "10YFR-RTE------C"        # ENTSO-E EIC for the France bidding zone (validated 2026-08-28)

MARKET = Market.make("fr", PARIS, fetch_entsoe.make_fetch(FR, PARIS),
                     deadline_hour=12, currency="EUR",
                     presentation=Presentation(
                         title="French (FR) day-ahead battery arbitrage",
                         tab_name="France", tz_label="Paris",
                         source="ENTSO-E (private use; prices not redistributed)"))
