"""The registry of markets the loop runs. Spain (ES) is the primary, live
public ledger; DE and ERCOT are silent shadow ledgers (build 2026-08-22),
IT is derived-metrics-only (prices held privately, not republished).

Each market carries its own timezone, commit deadline (local clock, before
its auction publishes), currency, Data/<slug>/ tree, and fetch client. The
strategy panel, P&L math, and guards in loop.py are market-agnostic.
"""
from __future__ import annotations

from . import fetch_ercot, fetch_smard
from .fetch import fetch_hourly as fetch_es
from .loop import DATA_DIR, LEDGER, PRICES, RECEIPTS, MARKET_TZ, Market

# Spain: the primary. Uses repo-root Data/ paths (not Data/es/) for
# continuity with the existing live ledger.
ES = Market("es", MARKET_TZ, 13, "EUR", PRICES, RECEIPTS, LEDGER, fetch_es)

# Germany (DE-LU): SMARD.de, CC BY 4.0. Auction gate closes 12:00 CET.
DE = Market.make("de", "Europe/Berlin", fetch_smard.fetch_hourly,
                 deadline_hour=12, currency="EUR")

# ERCOT (Texas): DAM SPP, hub HB_NORTH, USD. DAM bid deadline 10:00 CT —
# commit before the auction closes.
ERCOT = Market.make("ercot", "America/Chicago",
                    fetch_ercot.make_fetch("HB_NORTH"),
                    deadline_hour=10, currency="USD")

# Registry by slug. IT (derived-metrics-only) is added when its fetcher +
# mirror-redaction land.
MARKETS = {m.slug: m for m in (ES, DE, ERCOT)}
