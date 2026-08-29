"""Market CONFORMANCE contract — the integrity cure (adopted 2026-08-28).

The one harm that matters for this project is a market going live MISSING a guard:
IT/PT shipped 2026-08-28 without a deadline fixture test. This battery is
parametrized over the LIVE registry, so a newly-registered market that lacks any
guard FAILS CI rather than committing broken. Adding a market cannot half-onboard
it — every market here is checked for the same guards, automatically.

Scope: CORRECTNESS-of-config + the clock guard (static, hermetic). LIVENESS — did
every market that should commit actually commit? — is a RUNTIME concern (a silent
stop is invisible to a unit test); that is Pillar B, the staleness monitor, not
this file.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

import talea.loop as loop
from talea import markets as reg
from talea.loop import tick

MARKETS = list(reg.MARKETS.values())
IDS = [m.slug for m in MARKETS]


def _flat_day(d: str, base: float = 60.0, cheap=(3, 4), dear=(20, 21)) -> dict[str, float]:
    prices = [base] * 24
    for h in cheap:
        prices[h] = base - 50
    for h in dear:
        prices[h] = base + 50
    return {f"{d}T{h:02d}": p for h, p in enumerate(prices)}


def test_exactly_one_primary():
    """The heartbeat and every 'the primary' consumer assume a unique primary."""
    assert sum(1 for m in MARKETS if m.primary) == 1


@pytest.mark.parametrize("m", MARKETS, ids=IDS)
def test_market_config_invariants(m):
    assert 0 <= m.deadline_hour <= 23, f"{m.slug} deadline_hour out of range"
    assert m.currency and m.currency.isupper() and len(m.currency) == 3, \
        f"{m.slug} currency not a 3-letter code"
    assert callable(m.fetch), f"{m.slug} has no fetch callable wired"
    # LICENSE: you may only PUBLICLY mirror data you are allowed to redistribute.
    # This is the guard against an IT/PT-style price-redistribution leak.
    if m.public:
        assert m.redistributable, \
            f"{m.slug} is public but not redistributable — license-leak risk"
        assert m.presentation.title and m.presentation.tz_label, \
            f"{m.slug} is public but its presentation is incomplete (title/tz_label)"
    # PATH ISOLATION: a non-primary market lives entirely under Data/<slug>/.
    if not m.primary:
        assert m.slug in str(m.receipts_path.parent), \
            f"{m.slug} receipts are not isolated under its own dir"
        assert m.slug in str(m.ledger_path.parent), \
            f"{m.slug} ledger is not isolated under its own dir"


@pytest.mark.parametrize("m", MARKETS, ids=IDS)
def test_clock_guard_fires_at_each_market_deadline(m, tmp_path):
    """Every registered market's clock guard must REFUSE a commit at/after its
    deadline in ITS OWN timezone, and ALLOW one before. Generalizes the IT/PT
    detector to the whole registry: PT's Europe/Lisbon runs an hour behind
    Rome/Madrid, so its 12:00-local deadline is a distinct wall-clock instant —
    and so is any future market's (GB 11:00 London, JEPX 10:00 JST, ...). A market
    whose deadline is mis-wired against its auction is the classic leak path; this
    makes it impossible to add one silently."""
    day = _flat_day("2026-08-01")
    common = dict(fetch=lambda a, b: day, today=date(2026, 8, 1), sleep=lambda _s: None)

    # AT/after the deadline (market-local): clock guard refuses, no receipt.
    late_mkt = loop.Market.make(m.slug, m.tz, fetch=None, deadline_hour=m.deadline_hour,
                                currency=m.currency, root=tmp_path / f"{m.slug}_late")
    s_no = tick(market=late_mkt,
                now_fn=lambda: datetime(2026, 8, 1, m.deadline_hour, 30, tzinfo=late_mkt.tz),
                **common)
    assert s_no["committed"] == [], f"{m.slug} committed past its deadline"
    assert any("clock guard" in x for x in s_no["skipped"]), \
        f"{m.slug} clock guard did not fire at its {m.deadline_hour}:00 deadline"

    # Before the deadline: the same state commits fine (only meaningful when the
    # deadline leaves an earlier same-day hour, i.e. deadline_hour > 0).
    if m.deadline_hour > 0:
        early_mkt = loop.Market.make(m.slug, m.tz, fetch=None, deadline_hour=m.deadline_hour,
                                     currency=m.currency, root=tmp_path / f"{m.slug}_early")
        s_ok = tick(market=early_mkt,
                    now_fn=lambda: datetime(2026, 8, 1, m.deadline_hour - 1, 5, tzinfo=early_mkt.tz),
                    **common)
        assert s_ok["committed"], f"{m.slug} refused a commit before its deadline"
