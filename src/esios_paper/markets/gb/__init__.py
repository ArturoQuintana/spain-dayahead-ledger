"""Great Britain (GB) — day-ahead Market Index via Elexon BMRS. REDISTRIBUTABLE
(Elexon Insights open data — same public tier as ES/DE), but launching SILENT-FIRST:
`public=False` until the licence evidence is confirmed to your bar, then flip to a
public mirror. `redistributable=True` records that the licence permits publication.

Post-Brexit GB runs its own day-ahead auction (decoupled from SDAC); prices publish
~10:00 UTC — far earlier than the CET markets — so the 11:00-Madrid tick (=10:00
London) commits tomorrow's receipt before publication, with the dataset-relative
leak guard as the real gate. deadline_hour=11 (London) backstops the summer
publication; winter (publication ≈ tick time) leans on the leak guard.

Dedicated client (`markets/gb/fetch.py`, the BMRS Market Index parser). Built to
Elexon's documented schema; VALIDATE live before it commits (no recorded fixture
yet — the parser is schema-tolerant). First market added on the finished plugin
architecture (2026-08-28); the shortlist's #1 (public anchor, open-licence).
"""
from __future__ import annotations

from ..base import Market, Presentation
from .fetch import fetch_hourly

MARKET = Market.make("gb", "Europe/London", fetch_hourly,
                     deadline_hour=11, currency="GBP",
                     public=True, redistributable=True,
                     presentation=Presentation(
                         title="GB day-ahead battery arbitrage",
                         tab_name="Great Britain", tz_label="London",
                         source="Elexon BMRS Market Index (Insights, open data)"))
