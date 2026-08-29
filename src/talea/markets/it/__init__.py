"""Italy (IT-SUD) — ENTSO-E day-ahead, DERIVED-METRICS-ONLY (prices never
republished), private. SDAC-coupled, gate 12:00 CET, Europe/Rome.

An INDEPENDENT market on the shared ENTSO-E A44 library (`markets/_entsoe.py`):
owns its bidding-zone EIC + timezone and binds the library inline — no `fetch.py`
(shared library, no own logic). Migrated inline -> vertical module in Phase 2
(2026-08-28), decoupling it from PT (they no longer live in one shared module).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from ..base import Market, Presentation
from .._entsoe import make_fetch

ROME = ZoneInfo("Europe/Rome")
IT_SUD = "10Y1001A1001A73I"       # ENTSO-E EIC for bidding zone IT-SUD

MARKET = Market.make("it", ROME, make_fetch(IT_SUD, ROME),
                     deadline_hour=12, currency="EUR",
                     presentation=Presentation(
                         title="Italian (IT-SUD) day-ahead battery arbitrage",
                         tab_name="Italy", tz_label="Rome",
                         source="ENTSO-E (private use; prices not redistributed)"))
