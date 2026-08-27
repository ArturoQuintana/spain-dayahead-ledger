"""Cross-market backtest: does the persistence/climatology story hold across
markets? Runs the EXACT live strategy functions (loop.STRATEGIES) over each
market's own price history (Data/<slug>/prices.json), same costs, and reports
pooled capture + mean tau per strategy per market over the shared window.

The live ledgers only have days; this reuses the ~7 months each market was
seeded with to ask the historical question the live data only hints at.
Analysis only — touches no receipts, no ledger.

Run: uv run python scripts/backtest_markets.py
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from esios_paper.loop import (STRATEGIES, day_profile, kendall_tau,  # noqa: E402
                              pick_hours, pnl_eur)

ROOT = Path(__file__).resolve().parents[1]
MARKETS = {"es": ("Data/prices.json", "EUR"), "de": ("Data/de/prices.json", "EUR"),
           "it": ("Data/it/prices.json", "EUR"), "pt": ("Data/pt/prices.json", "EUR"),
           "ercot": ("Data/ercot/prices.json", "USD")}


def load(path: str) -> dict[str, float]:
    p = ROOT / path
    if not p.exists():
        return {}
    return {r["ts"]: r["price"] for r in json.loads(p.read_text())}


def backtest(prices: dict[str, float]) -> dict:
    days = sorted({ts[:10] for ts in prices})
    acc: dict[str, dict] = {s["strategy"]: {"pnl": 0.0, "orc": 0.0, "taus": [],
                                            "n": 0, "loss": 0} for s in STRATEGIES}
    for d_iso in days:
        target = date.fromisoformat(d_iso)
        actual = day_profile(prices, target)
        if len(actual) < 23:
            continue
        oracle = pnl_eur(*pick_hours(actual), actual)
        if oracle <= 0:
            continue
        basis_day = target - timedelta(days=1)
        for spec in STRATEGIES:
            basis, _ = spec["basis_fn"](prices, basis_day)
            if basis is None:
                continue
            buy, sell = pick_hours(basis)
            if not all(h in actual for h in buy + sell):
                continue
            pnl = pnl_eur(buy, sell, actual)
            a = acc[spec["strategy"]]
            a["pnl"] += pnl; a["orc"] += oracle; a["n"] += 1
            a["loss"] += pnl <= 0
            hours = sorted(h for h in basis if h in actual)
            t = kendall_tau([basis[h] for h in hours], [actual[h] for h in hours])
            if t is not None:
                a["taus"].append(t)
    return acc


def main() -> None:
    print(f"{'market':7} {'strategy':26} {'days':>4} {'pooled_cap':>10} "
          f"{'mean_tau':>8} {'loss_days':>9}")
    for slug, (path, cur) in MARKETS.items():
        prices = load(path)
        if not prices:
            print(f"{slug:7} (no price history)")
            continue
        acc = backtest(prices)
        for spec in STRATEGIES:
            a = acc[spec["strategy"]]
            if a["n"] == 0:
                continue
            cap = 100 * a["pnl"] / a["orc"] if a["orc"] else 0
            tau = statistics.fmean(a["taus"]) if a["taus"] else float("nan")
            name = spec["strategy"].replace("battery-2h2h-", "")
            print(f"{slug:7} {name:26} {a['n']:>4} {cap:>9.1f}% {tau:>8.3f} "
                  f"{a['loss']:>9}")
        print()


if __name__ == "__main__":
    main()
