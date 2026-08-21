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
TIE_EPS = 0.01  # EUR — deltas below this are ties, excluded from the test


def sign_test_p(wins: int, n: int) -> float:
    """One-sided binomial P(X >= wins | n, 0.5)."""
    return sum(comb(n, i) for i in range(wins, n + 1)) / 2 ** n


def main() -> int:
    a = sys.argv[1] if len(sys.argv) > 1 else "battery-2h2h-climatology"
    b = sys.argv[2] if len(sys.argv) > 2 else "battery-2h2h-persistence"
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    by_day: dict[str, dict[str, float]] = {}
    for r in rows:
        by_day.setdefault(r["target"], {})[r["strategy"]] = r["pnl_eur"]
    deltas = [(d, v[a] - v[b]) for d, v in sorted(by_day.items())
              if a in v and b in v]
    if not deltas:
        print(f"no shared settled days between {a} and {b}")
        return 1
    wins = sum(1 for _, x in deltas if x > TIE_EPS)
    losses = sum(1 for _, x in deltas if x < -TIE_EPS)
    ties = len(deltas) - wins - losses
    n = wins + losses
    total = sum(x for _, x in deltas)
    print(f"{a}  vs  {b}")
    print(f"shared settled days: {len(deltas)} ({wins} wins, {losses} losses, "
          f"{ties} ties) | total delta {total:+.2f} EUR "
          f"({total / len(deltas):+.2f}/day)")
    if n == 0:
        print("verdict: all ties — no evidence either way")
        return 0
    p = sign_test_p(wins, n)
    print(f"sign test (one-sided, ties excluded): p = {p:.4f} on n = {n}")
    if n >= 30 and p < 0.05:
        print(f"verdict: PRE-REGISTERED BAR MET — {a} beats {b}")
    else:
        print(f"verdict: bar NOT met (needs n>=30 non-tied days and p<0.05; "
              f"have n={n}, p={p:.3f}) — no claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
