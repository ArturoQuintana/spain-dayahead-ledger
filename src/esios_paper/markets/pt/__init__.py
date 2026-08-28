"""Portugal (PT) — the other half of MIBEL, real PT-zone prices via ENTSO-E (NOT an
ES relabel). DERIVED-METRICS-ONLY (prices never republished), private. SDAC-coupled,
gate 12:00 CET, Europe/Lisbon (an hour behind Rome/Madrid).

An INDEPENDENT market on the shared ENTSO-E A44 library (`markets/_entsoe.py`):
owns its bidding-zone EIC + timezone and binds the library inline — no `fetch.py`.
Migrated inline -> vertical module in Phase 2 (2026-08-28); with IT already
migrated, `markets/_entsoe.py` now holds NO market-specific constants — IT and PT
are fully independent.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from ..base import Market, Presentation
from .._entsoe import make_fetch

LISBON = ZoneInfo("Europe/Lisbon")
PT = "10YPT-REN------W"            # ENTSO-E EIC for bidding zone Portugal

MARKET = Market.make("pt", LISBON, make_fetch(PT, LISBON),
                     deadline_hour=12, currency="EUR",
                     presentation=Presentation(
                         title="Portuguese (PT) day-ahead battery arbitrage",
                         tab_name="Portugal", tz_label="Lisbon",
                         source="ENTSO-E (private use; prices not redistributed)"))
