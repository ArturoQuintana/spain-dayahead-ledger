"""The registry of markets the loop runs — the SINGLE SOURCE OF TRUTH.

Each market carries its own timezone, commit deadline (local clock, before its
auction publishes), currency, Data/<slug>/ tree, fetch client, and FLAGS
(primary/public/driver/redistributable + presentation). Operational surfaces —
the email digest, server_tick.sh, render_dashboard.py, publish_mirror.sh, the
ARCHITECTURE Markets table — query this registry and branch on the flags rather
than hardcoding slug subsets (Phase 0 of the market-plugin refactor, 2026-08-27;
before it there were five drifting hand-synced lists).

Phase 1 (2026-08-28): `markets.py` became the `markets/` package. The public API
(`MARKETS`, `shadows`, `public_markets`, `by_driver`, and the contract types) is
unchanged, so every `from esios_paper.markets import …` keeps working. The
contract now lives in `base.py`; per-market plugins (`markets/<slug>/`) land here
in later phases.
"""
from __future__ import annotations

from .. import fetch_entsoe, fetch_ercot
from ..fetch import fetch_hourly as fetch_es
from ..loop import DATA_DIR, LEDGER, PRICES, RECEIPTS, MARKET_TZ
from .base import Fetcher, Market, Presentation  # the contract surface

__all__ = ["MARKETS", "shadows", "public_markets", "by_driver",
           "Market", "Presentation", "Fetcher"]

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

# Germany (DE-LU): SMARD.de, CC BY 4.0. Public. Gate 12:00 CET. Migrated to a
# vertical markets/de/ module in Phase 2 (2026-08-28) — imported, not inline.
from .de import MARKET as DE  # noqa: E402

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

# France (FR): the first market as a VERTICAL markets/<slug>/ module (Phase 1.5,
# 2026-08-28) — imported, not defined inline. ENTSO-E derived-only/private like
# IT/PT; flagship of the SDAC FR/BE/NL cluster. The incumbents above migrate into
# this same shape in Phase 2.
from .fr import MARKET as FR  # noqa: E402

# Registry by slug. Order: primary first, then shadows in digest order (ENTSO-E
# EU-derived markets it/pt/fr grouped; ERCOT — the USD/Actions market — last).
MARKETS = {m.slug: m for m in (ES, DE, IT, PT, FR, ERCOT)}


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
