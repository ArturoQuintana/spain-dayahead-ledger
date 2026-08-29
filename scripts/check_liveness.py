"""Pillar B — market LIVENESS monitor (adopted 2026-08-28).

`verify_ledger` checks that the receipts that EXIST are correct. It is structurally
incapable of noticing a market that silently STOPPED committing — a dead systemd
timer, a broken fetcher, a revoked API key — because a market that writes nothing
has nothing to verify. That blind spot is the one integrity harm that matters: a
silently-dark market rots the benchmark while every other check stays green. This
monitor closes it.

For every REGISTERED market it measures hours since the newest `committed_at`:
- HEALTHY : a receipt within --stale-hours (default 48h; a daily market sits ~24h).
- STALE   : nothing in >threshold  → two consecutive missed days → the writer has
            stopped. Exit is non-zero so a caller can page.
- NEVER   : registered but zero receipts (onboarding, or a first receipt that never
            fired) → reported, but does NOT fail the exit (onboarding is expected).

Unlike `verify_ledger` (deliberately app-independent, disk-driven, checks
CORRECTNESS), this MUST read the registry — the whole point is to notice a market
that SHOULD be committing and isn't, which only the registry knows (COMPLETENESS).

Run: uv run python scripts/check_liveness.py [--stale-hours 48] [--quiet]
Exit 1 if any registered market is STALE.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from talea import markets as registry  # noqa: E402
from talea.loop import load_prices  # noqa: E402

STALE_HOURS = 48.0
PRICE_STALE_DAYS = 2   # a market whose NEWEST PRICE is older than this has a
# broken/stalled fetch. This catches the class the receipt-only check misses: a
# LAUNCHED market whose fetcher silently fails commits nothing, so it hides as the
# exempt NEVER even though it is actually broken (e.g. GB's Elexon 7-day-window
# 400s, 2026-08-29 — invisible to every check because a market with no data has
# nothing to verify AND no receipt to be "stale"). Stale prices are unambiguous:
# a working day-ahead fetch always advances to ~today/tomorrow.


def newest_price_date(prices_path: Path) -> date | None:
    """Newest local price date in a market's dataset, or None if it has none."""
    prices = load_prices(prices_path)
    return date.fromisoformat(max(prices)[:10]) if prices else None


def newest_commit(receipts_path: Path) -> datetime | None:
    """The most recent committed_at across a market's receipts, or None if the
    market has never committed (missing file or empty)."""
    if not receipts_path.exists():
        return None
    stamps = []
    for line in receipts_path.read_text().splitlines():
        line = line.strip()
        if line:
            ca = json.loads(line).get("committed_at")
            if ca:
                stamps.append(datetime.fromisoformat(ca))
    return max(stamps) if stamps else None


def market_liveness(slug: str, receipts_path: Path, now: datetime,
                    stale_hours: float = STALE_HOURS,
                    prices_path: Path | None = None) -> dict:
    npd = newest_price_date(prices_path) if prices_path is not None else None
    price_age_d = (now.date() - npd).days if npd is not None else None
    fetch_stale = price_age_d is not None and price_age_d > PRICE_STALE_DAYS
    nc = newest_commit(receipts_path)
    if nc is None:
        # NEVER-committed: normally exempt (onboarding), BUT if its prices have
        # gone stale the fetcher is broken, not onboarding — that is STALE.
        return {"slug": slug, "last_commit": None, "age_h": None,
                "price_age_d": price_age_d, "fetch_stale": fetch_stale,
                "state": "STALE" if fetch_stale else "NEVER"}
    age_h = (now - nc).total_seconds() / 3600.0
    stale = age_h > stale_hours or fetch_stale
    return {"slug": slug, "last_commit": nc, "age_h": age_h,
            "price_age_d": price_age_d, "fetch_stale": fetch_stale,
            "state": "STALE" if stale else "HEALTHY"}


def assess(markets, now: datetime, stale_hours: float = STALE_HOURS) -> list[dict]:
    return [market_liveness(m.slug, m.receipts_path, now, stale_hours,
                            prices_path=getattr(m, "prices_path", None))
            for m in markets]


def _fmt(r: dict) -> str:
    if r["state"] == "NEVER":
        return f"  NEVER    {r['slug']:6} — no receipts yet"
    if r.get("fetch_stale"):
        return (f"  STALE    {r['slug']:6} — prices {r['price_age_d']}d stale "
                f"(fetcher stopped)")
    return f"  {r['state']:8} {r['slug']:6} — last commit {r['age_h']:.1f}h ago"


def main(argv: list[str] | None = None, market_list=None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-market liveness monitor.")
    ap.add_argument("--stale-hours", type=float, default=STALE_HOURS)
    ap.add_argument("--quiet", action="store_true", help="print only problems")
    a = ap.parse_args(argv)

    now = now or datetime.now(timezone.utc)
    markets = market_list if market_list is not None else list(registry.MARKETS.values())
    rows = assess(markets, now, a.stale_hours)
    stale = [r for r in rows if r["state"] == "STALE"]
    never = [r for r in rows if r["state"] == "NEVER"]

    for r in rows:
        if not a.quiet or r["state"] != "HEALTHY":
            print(_fmt(r))
    if stale:
        print(f"-> STALE (writer or fetcher stopped): "
              f"{', '.join(r['slug'] for r in stale)}")
    elif never:
        print(f"-> all live; NEVER (info): {', '.join(r['slug'] for r in never)}")
    else:
        print("-> all markets live")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
