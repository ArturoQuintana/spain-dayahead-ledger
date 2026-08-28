"""The registry of markets the loop runs — the SINGLE SOURCE OF TRUTH.

Each market carries its own timezone, commit deadline (local clock, before its
auction publishes), currency, Data/<slug>/ tree, fetch client, and FLAGS
(primary/public/driver/redistributable + presentation). Operational surfaces —
the email digest, server_tick.sh, render_dashboard.py, publish_mirror.sh, the
ARCHITECTURE Markets table — query this registry and branch on the flags rather
than hardcoding slug subsets (Phase 0 of the market-plugin refactor, 2026-08-27;
before it there were five drifting hand-synced lists).
"""
from __future__ import annotations

from . import fetch_entsoe, fetch_ercot, fetch_smard
from .fetch import fetch_hourly as fetch_es
from .loop import (DATA_DIR, LEDGER, PRICES, RECEIPTS, MARKET_TZ, Market,
                   Presentation)

# Spain: the primary. Repo-root Data/ paths (not Data/es/) for continuity with
# the existing live ledger; public, Bitcoin-anchored, its receipt drives the
# heartbeat. Presentation strings are the byte-for-byte source render_dashboard
# used to hold — the public page must not change.
ES = Market("es", MARKET_TZ, 13, "EUR", PRICES, RECEIPTS, LEDGER, fetch_es,
            primary=True, public=True, redistributable=True,
            presentation=Presentation(
                title="Spanish day-ahead battery arbitrage",
                tab_name="Spain", tz_label="Madrid", show_gate=True,
                source="apidatos.ree.es,\n      cross-checked weekly against "
                       "the independent token ESIOS route"))

# Germany (DE-LU): SMARD.de, CC BY 4.0. Public. Auction gate closes 12:00 CET.
DE = Market.make("de", "Europe/Berlin", fetch_smard.fetch_hourly,
                 deadline_hour=12, currency="EUR", public=True,
                 redistributable=True,
                 presentation=Presentation(
                     title="German (DE-LU) day-ahead battery arbitrage",
                     tab_name="Germany", tz_label="Berlin",
                     source="Bundesnetzagentur | SMARD.de (CC BY 4.0)"))

# Italy (IT-SUD): ENTSO-E, DERIVED-METRICS-ONLY (prices never republished).
# Private. SDAC-coupled, gate 12:00 CET.
IT = Market.make("it", "Europe/Rome", fetch_entsoe.fetch_hourly,
                 deadline_hour=12, currency="EUR",
                 presentation=Presentation(
                     title="Italian (IT-SUD) day-ahead battery arbitrage",
                     tab_name="Italy", tz_label="Rome",
                     source="ENTSO-E (private use; prices not redistributed)"))

# Portugal (PT): the other half of MIBEL — real PT-zone prices (ENTSO-E), NOT
# an ES relabel. Derived-only/private like Italy. Europe/Lisbon.
PT = Market.make("pt", "Europe/Lisbon",
                 fetch_entsoe.make_fetch(fetch_entsoe.PT, fetch_entsoe.LISBON),
                 deadline_hour=12, currency="EUR",
                 presentation=Presentation(
                     title="Portuguese (PT) day-ahead battery arbitrage",
                     tab_name="Portugal", tz_label="Lisbon",
                     source="ENTSO-E (private use; prices not redistributed)"))

# ERCOT (Texas): DAM SPP, hub HB_NORTH, USD. Redistributable (NP4-190 public),
# but geo-blocks EU IPs -> driven from GitHub Actions US runners, not the server.
ERCOT = Market.make("ercot", "America/Chicago",
                    fetch_ercot.make_fetch("HB_NORTH"),
                    deadline_hour=10, currency="USD", driver="actions",
                    redistributable=True,
                    presentation=Presentation(
                        title="ERCOT (HB_NORTH) day-ahead battery arbitrage",
                        tab_name="ERCOT", tz_label="Chicago",
                        source="ERCOT public data (NP4-190, DAM SPP)"))

# Registry by slug. Order: primary first, then shadows in digest order.
MARKETS = {m.slug: m for m in (ES, DE, IT, PT, ERCOT)}


# --- registry queries: the ONLY way operational surfaces should enumerate ---

def shadows() -> list[Market]:
    """Non-primary markets, in registry order (the email digest's set)."""
    return [m for m in MARKETS.values() if not m.primary]


def public_markets() -> list[Market]:
    """Markets with a public mirror + dashboard (publish_mirror's set)."""
    return [m for m in MARKETS.values() if m.public]


def by_driver(driver: str) -> list[Market]:
    """Markets driven by `driver` ('server' | 'actions'); excludes the primary,
    which the ES pass runs directly (server_tick / Actions consumers)."""
    return [m for m in MARKETS.values() if m.driver == driver and not m.primary]
