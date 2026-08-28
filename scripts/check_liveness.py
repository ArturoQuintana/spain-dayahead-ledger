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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from esios_paper import markets as registry  # noqa: E402

STALE_HOURS = 48.0


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
                    stale_hours: float = STALE_HOURS) -> dict:
    nc = newest_commit(receipts_path)
    if nc is None:
        return {"slug": slug, "last_commit": None, "age_h": None, "state": "NEVER"}
    age_h = (now - nc).total_seconds() / 3600.0
    return {"slug": slug, "last_commit": nc, "age_h": age_h,
            "state": "STALE" if age_h > stale_hours else "HEALTHY"}


def assess(markets, now: datetime, stale_hours: float = STALE_HOURS) -> list[dict]:
    return [market_liveness(m.slug, m.receipts_path, now, stale_hours) for m in markets]


def _fmt(r: dict) -> str:
    if r["state"] == "NEVER":
        return f"  NEVER    {r['slug']:6} — no receipts yet"
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
        print(f"-> STALE: {', '.join(r['slug'] for r in stale)} "
              f"(no receipt in >{a.stale_hours:.0f}h)")
    elif never:
        print(f"-> all live; NEVER (info): {', '.join(r['slug'] for r in never)}")
    else:
        print("-> all markets live")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
