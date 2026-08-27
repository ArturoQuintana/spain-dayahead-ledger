"""The pre-registered strategy-comparison test (see CLAUDE.md § Deciding
strategy comparisons): one-sided sign test on paired daily P&L deltas over
shared settled days. Pairing cancels common day effects (both strategies face
the same prices); ties are excluded. The claim "A beats B" requires >=30
non-tied shared days AND p < 0.05 — cumulative EUR alone decides nothing.

Run: uv run python scripts/compare_strategies.py [strategy_a] [strategy_b]
Defaults: battery-2h2h-climatology vs battery-2h2h-persistence.
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "Data" / "ledger.jsonl"
# Pre-registered tie band (CLAUDE.md): |delta| < 0.01 EUR is a tie, excluded.
# Deltas are rounded to the 2-decimal P&L domain before comparison so the
# boundary is float-deterministic; a rounded +/-0.01 is a genuine (if tiny)
# directional difference and counts, matching the doctrine's strict "< 0.01".
TIE_EPS = 0.01


def sign_test_p(wins: int, n: int) -> float:
    """One-sided binomial P(X >= wins | n, 0.5)."""
    return sum(comb(n, i) for i in range(wins, n + 1)) / 2 ** n


def evaluate(rows: list[dict], a: str, b: str) -> dict:
    """The pure decision: pair A vs B on shared settled days, run the one-sided
    sign test on non-tied paired deltas, apply the pre-registered bar. Separated
    from I/O so the governance-critical boundary (>=30 non-tied days AND p<0.05)
    is unit-testable. `p` is None when there are no non-tied days."""
    by_day: dict[str, dict[str, float]] = {}
    for r in rows:
        by_day.setdefault(r["target"], {})[r["strategy"]] = r["pnl_eur"]
    deltas = [(d, round(v[a] - v[b], 2)) for d, v in sorted(by_day.items())
              if a in v and b in v]
    wins = sum(1 for _, x in deltas if x >= TIE_EPS)
    losses = sum(1 for _, x in deltas if x <= -TIE_EPS)
    n = wins + losses
    p = sign_test_p(wins, n) if n > 0 else None
    return {"a": a, "b": b, "deltas": deltas, "shared": len(deltas),
            "wins": wins, "losses": losses, "ties": len(deltas) - wins - losses,
            "n": n, "total": sum(x for _, x in deltas), "p": p,
            "bar_met": bool(n >= 30 and p is not None and p < 0.05)}


def main() -> int:
    a = sys.argv[1] if len(sys.argv) > 1 else "battery-2h2h-climatology"
    b = sys.argv[2] if len(sys.argv) > 2 else "battery-2h2h-persistence"
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    r = evaluate(rows, a, b)
    if not r["deltas"]:
        print(f"no shared settled days between {a} and {b}")
        return 1
    print(f"{a}  vs  {b}")
    print(f"shared settled days: {r['shared']} ({r['wins']} wins, "
          f"{r['losses']} losses, {r['ties']} ties) | total delta "
          f"{r['total']:+.2f} EUR ({r['total'] / r['shared']:+.2f}/day)")
    if r["n"] == 0:
        print("verdict: all ties — no evidence either way")
        return 0
    print(f"sign test (one-sided, ties excluded): p = {r['p']:.4f} on n = {r['n']}")
    if r["bar_met"]:
        print(f"verdict: PRE-REGISTERED BAR MET — {a} beats {b}")
    else:
        print(f"verdict: bar NOT met (needs n>=30 non-tied days and p<0.05; "
              f"have n={r['n']}, p={r['p']:.3f}) — no claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
