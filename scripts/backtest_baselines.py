"""Backtest the pre-registered baselines over the deep dataset (2015-2026).

Answers the question the live ledger cannot: is the current month's capture
regime-typical, or is August 2026 flattering us? Runs the EXACT live logic
(loop.pick_hours / pnl_eur / kendall_tau, same costs) over
Data/esios_prices.json. Analysis only — touches no receipts, no ledger.

Conventions: the deep dataset stores DST-short/long days as dense lists, so
only 24-hour days are used as targets and bases (~2 days/year skipped, noted
in output). Climatology = per-hour mean over complete days in the trailing 28
ending the basis day (>=14 required), as in the live loop.

Run: uv run python scripts/backtest_baselines.py [--markdown docs/out.md]
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from talea.loop import (CLIM_MIN_DAYS, CLIM_WINDOW, N_HOURS,   # noqa: E402
                              kendall_tau, pick_hours, pnl_eur)

DEEP = Path(__file__).resolve().parents[1] / "Data" / "esios_prices.json"
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def load_days() -> dict[date, list[float]]:
    rows = json.loads(DEEP.read_text())
    out = {}
    for r in rows:
        d = datetime.strptime(r["date"], "%d/%m/%Y").date()
        out[d] = r["prices"]
    return out


def clim_basis(days: dict[date, list[float]], basis_day: date):
    window = [days[basis_day - timedelta(days=i)]
              for i in range(CLIM_WINDOW)
              if len(days.get(basis_day - timedelta(days=i), [])) == 24]
    if len(window) < CLIM_MIN_DAYS:
        return None
    return {h: statistics.fmean(d[h] for d in window) for h in range(24)}


def blend_basis(p_basis: dict[int, float], c_basis: dict[int, float]):
    hours = sorted(set(p_basis) & set(c_basis))

    def ranks(basis):
        order = sorted(hours, key=lambda h: (basis[h], h))
        return {h: i for i, h in enumerate(order)}
    rp, rc = ranks(p_basis), ranks(c_basis)
    return {h: (rp[h] + rc[h]) / 2 for h in hours}


def run() -> list[dict]:
    days = load_days()
    results, skipped_dst = [], 0
    for target in sorted(days):
        basis_day = target - timedelta(days=1)
        if len(days[target]) != 24 or len(days.get(basis_day, [])) != 24:
            skipped_dst += 1
            continue
        actual = {h: p for h, p in enumerate(days[target])}
        p_basis = {h: p for h, p in enumerate(days[basis_day])}
        c_basis = clim_basis(days, basis_day)
        if c_basis is None:
            continue
        b_basis = blend_basis(p_basis, c_basis)

        oracle_pnl = pnl_eur(*pick_hours(actual), actual)
        by_price = sorted(actual.values())
        row = {"target": target, "year": target.year,
               "season": SEASON[target.month],
               "oracle": oracle_pnl,
               "neg_hours": sum(1 for p in by_price if p < 0),
               "tb2": round(sum(by_price[-2:]) - sum(by_price[:2]), 2),
               "tb4": round(sum(by_price[-4:]) - sum(by_price[:4]), 2)}
        for name, basis in [("pers", p_basis), ("clim", c_basis),
                            ("blend", b_basis)]:
            buy, sell = pick_hours(basis)
            pnl = pnl_eur(buy, sell, actual)
            hours = sorted(h for h in basis if h in actual)
            row[f"{name}_pnl"] = pnl
            row[f"{name}_cap"] = (pnl / oracle_pnl if oracle_pnl > 0 else None)
            row[f"{name}_tau"] = kendall_tau([basis[h] for h in hours],
                                             [actual[h] for h in hours])
        results.append(row)
    print(f"days evaluated: {len(results)} (skipped {skipped_dst} DST-adjacent)")
    return results


def agg(rows: list[dict], name: str) -> dict:
    caps = {s: [r[f"{s}_cap"] for r in rows if r[f"{s}_cap"] is not None]
            for s in ("pers", "clim", "blend")}
    taus = {s: [r[f"{s}_tau"] for r in rows if r[f"{s}_tau"] is not None]
            for s in ("pers", "clim", "blend")}
    return {
        "bucket": name, "days": len(rows),
        **{f"{s}_cap": round(statistics.fmean(caps[s]) * 100, 1)
           for s in caps if caps[s]},
        **{f"{s}_tau": round(statistics.fmean(taus[s]), 3)
           for s in taus if taus[s]},
        # pooled capture (sum pnl / sum oracle): robust where daily ratios
        # explode on near-zero-oracle days — the aggregate to trust
        **{f"{s}_pooled": round(100 * sum(r[f"{s}_pnl"] for r in rows)
                                / osum, 1)
           for s in ("pers", "clim", "blend")
           if (osum := sum(r["oracle"] for r in rows)) > 0},
        "pers_pnl": round(statistics.fmean([r["pers_pnl"] for r in rows]), 1),
        "oracle": round(statistics.fmean([r["oracle"] for r in rows]), 1),
        "pers_losing_days_pct": round(100 * sum(
            r["pers_pnl"] <= 0 for r in rows) / len(rows), 1),
        "neg_hours": round(statistics.fmean([r["neg_hours"] for r in rows]), 2),
        "tb2": round(statistics.fmean([r["tb2"] for r in rows]), 1),
        "tb4_over_tb2": round(statistics.fmean(
            [r["tb4"] / r["tb2"] for r in rows if r["tb2"] > 0]), 2),
    }


def main() -> None:
    rows = run()
    buckets = [agg(rows, "ALL 2015-2026")]
    for y in sorted({r["year"] for r in rows}):
        buckets.append(agg([r for r in rows if r["year"] == y], str(y)))
    for s in ("DJF", "MAM", "JJA", "SON"):
        buckets.append(agg([r for r in rows if r["season"] == s], s))
    # season x recent years: the gate-relevant slices
    for y in (2024, 2025, 2026):
        for s in ("DJF", "MAM", "JJA", "SON"):
            sub = [r for r in rows if r["year"] == y and r["season"] == s]
            if sub:
                buckets.append(agg(sub, f"{y}-{s}"))
    cols = ["bucket", "days", "pers_pooled", "clim_pooled", "blend_pooled",
            "pers_tau", "clim_tau", "blend_tau", "pers_pnl", "oracle",
            "pers_losing_days_pct", "neg_hours", "tb2", "tb4_over_tb2"]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "---|" * len(cols)]
    for b in buckets:
        lines.append("| " + " | ".join(str(b.get(c, "")) for c in cols) + " |")
    table = "\n".join(lines)
    print(table)
    if "--markdown" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--markdown") + 1])
        out.write_text(
            "# Baseline backtest over the deep dataset (generated by "
            "scripts/backtest_baselines.py)\n\n"
            "Capture in % of the TB2 perfect-hindsight oracle (net of 85% RT "
            "+ fees, same as the live ledger); tau = Kendall tau-b of basis "
            "vs actual; tb2/tb4 = gross spreads EUR; pnl/oracle = EUR/day "
            "for the 1 MW / 2 MWh battery.\n\n" + table + "\n")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
