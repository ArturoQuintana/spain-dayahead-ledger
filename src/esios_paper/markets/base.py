"""The market CONTRACT — the stable surface every market plugin is written
against (Phase 1 of the market-plugin refactor, 2026-08-28).

`Market` and `Presentation` are defined in `loop.py` and stay there: `loop.py`
(tick, guards, P&L math, storage) is the market-agnostic core and is a
non-negotiable no-change zone. This module RE-EXPORTS them as the package's
contract surface — so a `markets/<slug>/` plugin imports its types from
`.base`, not by reaching into the core — and adds the `Fetcher` protocol that
pins the one behaviour a market must supply. (The eventual physical relocation
of `Market` into this module, if ever, is bundled into the Phase-2 loop.py touch
that moves ES's default construction out of the core — never a standalone edit.)
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..loop import Market, Presentation

__all__ = ["Market", "Presentation", "Fetcher"]


@runtime_checkable
class Fetcher(Protocol):
    """What every market's `fetch` callable must satisfy: given an inclusive
    [start, end] date range, return {ISO-hour-key: price} in the market's local
    clock frame (quarter-hour sources aggregated to hourly upstream). This is the
    one behavioural contract the tick depends on; a market plugin supplies it."""

    def __call__(self, start: date, end: date) -> dict[str, float]: ...
