#!/usr/bin/env python3
"""Reproduce the founding signal probe (2026-07-29) on the deep dataset.

The project's headline claim (README/CLAUDE.md): on 182 days of hourly spot
prices, "persistence beats a day-shuffled null by 12.8sigma, ACF(lag 1h) =
+0.94, and climatology loses 2.2x — the structure is temporal." This script
re-derives those three numbers from Data/esios_prices.json with an explicit,
deterministic methodology, on BOTH the original ~182-day window (to check the
cited figures) and the full 11.5 years (to see whether the signal holds out of
the founding sample). Integrity exercise: regenerate the number on command, or
stop quoting it. stdlib-only; fixed RNG seed → byte-reproducible.

    uv run python scripts/probe_signal.py

Methodology (stated so it can be argued with):
  ACF(lag 1h)  Pearson autocorrelation of the contiguous hourly price series at
               a 1-hour lag.
  persistence  A day's shape is its 24 hourly prices. S = mean Pearson
  vs shuffled  correlation between each pair of CONSECUTIVE calendar days'
  null (sigma) shapes. The day-shuffled null permutes day order and recomputes
               S; z = (S_obs - mean_null) / std_null over K permutations. Tests
               directly: are adjacent days more alike than random days?
  climatology  Next-day prediction error (RMSE, EUR/MWh) of two predictors of
  loses N x    day t's 24h profile: persistence = day t-1; climatology =
               per-hour mean of the trailing 28 complete days. Ratio
               RMSE_clim / RMSE_persist on the shared eligible day set.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "Data" / "esios_prices.json"
PROBE_END = date(2026, 7, 29)   # the founding probe date
PROBE_DAYS = 182
K_PERM = 2000                   # day-shuffle permutations for the null
SEED = 0


def load_days() -> list[tuple[date, list[float]]]:
    raw = json.loads(DATA.read_text())
    out = []
    for rec in raw:
        d, m, y = rec["date"].split("/")
        prices = rec["prices"]
        if len(prices) == 24 and all(isinstance(p, (int, float)) for p in prices):
            out.append((date(int(y), int(m), int(d)), [float(p) for p in prices]))
    out.sort(key=lambda t: t[0])
    return out


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sxx * syy)


def acf_lag1(days: list[tuple[date, list[float]]]) -> float:
    # contiguous hourly series over consecutive calendar days only
    series: list[float] = []
    prev = None
    for d, prices in days:
        if prev is not None and d - prev == timedelta(days=1):
            series.extend(prices)
        else:                       # start a fresh contiguous run
            series = series + prices if not series else series
        prev = d
    # simpler & robust: flatten all, autocorr across the whole vector
    flat = [p for _, prices in days for p in prices]
    r = pearson(flat[:-1], flat[1:])
    return r if r is not None else float("nan")


def adjacent_shape_corrs(days) -> list[float]:
    """Pearson corr of each pair of consecutive-calendar-day shapes."""
    cs = []
    for (d0, p0), (d1, p1) in zip(days, days[1:]):
        if d1 - d0 == timedelta(days=1):
            r = pearson(p0, p1)
            if r is not None:
                cs.append(r)
    return cs


def persistence_sigma(days) -> dict:
    obs = adjacent_shape_corrs(days)
    s_obs = sum(obs) / len(obs)
    shapes = [p for _, p in days]
    rng = random.Random(SEED)
    null_means = []
    idx = list(range(len(shapes)))
    for _ in range(K_PERM):
        rng.shuffle(idx)
        perm = [shapes[i] for i in idx]
        rs = [pearson(perm[i], perm[i + 1]) for i in range(len(perm) - 1)]
        rs = [r for r in rs if r is not None]
        null_means.append(sum(rs) / len(rs))
    mu = sum(null_means) / len(null_means)
    var = sum((m - mu) ** 2 for m in null_means) / (len(null_means) - 1)
    sd = math.sqrt(var)
    z = (s_obs - mu) / sd if sd > 0 else float("inf")
    return {"s_obs": s_obs, "null_mu": mu, "null_sd": sd, "z": z, "n_pairs": len(obs)}


def _pick2(profile: list[float]) -> tuple[list[int], list[int]]:
    order = sorted(range(24), key=lambda h: (profile[h], h))
    return order[:2], order[-2:]


def _pnl(buy, sell, actual) -> float:
    return round(sum(actual[h] * 0.85 for h in sell)
                 - sum(actual[h] for h in buy) - 0.5 * (2 + 1.7), 2)


def climatology_ratio(days) -> dict:
    """Compare persistence vs 28-day climatology as next-day predictors, across
    several metrics — because 'loses 2.2x' is only meaningful once you say at
    WHAT. Level error (RMSE/MSE/MAE), demeaned-shape error, and the arbitrage
    capture the strategy actually optimizes."""
    by_date = {d: p for d, p in days}
    ep_sq = ec_sq = ep_l1 = ec_l1 = ep_sh = ec_sh = 0.0
    cap_p = cap_c = n_orc = 0.0
    n = 0
    for d, actual in days:
        prev = d - timedelta(days=1)
        window = [by_date[d - timedelta(days=k)] for k in range(1, 29)
                  if d - timedelta(days=k) in by_date]
        if prev not in by_date or len(window) < 28:
            continue
        clim = [sum(w[h] for w in window) / len(window) for h in range(24)]
        persist = by_date[prev]
        n += 1
        ep_sq += sum((actual[h] - persist[h]) ** 2 for h in range(24))
        ec_sq += sum((actual[h] - clim[h]) ** 2 for h in range(24))
        ep_l1 += sum(abs(actual[h] - persist[h]) for h in range(24))
        ec_l1 += sum(abs(actual[h] - clim[h]) for h in range(24))
        ma, mp, mc = sum(actual) / 24, sum(persist) / 24, sum(clim) / 24
        ep_sh += sum(((actual[h] - ma) - (persist[h] - mp)) ** 2 for h in range(24))
        ec_sh += sum(((actual[h] - ma) - (clim[h] - mc)) ** 2 for h in range(24))
        orc = _pnl(*_pick2(actual), actual)
        if orc > 0:
            cap_p += _pnl(*_pick2(persist), actual) / orc
            cap_c += _pnl(*_pick2(clim), actual) / orc
            n_orc += 1
    return {"n_days": n,
            "rmse_ratio": math.sqrt(ec_sq) / math.sqrt(ep_sq),
            "mse_ratio": ec_sq / ep_sq, "mae_ratio": ec_l1 / ep_l1,
            "shape_rmse_ratio": math.sqrt(ec_sh) / math.sqrt(ep_sh),
            "cap_persist": cap_p / n_orc, "cap_clim": cap_c / n_orc,
            "rmse_persist": math.sqrt(ep_sq / (n * 24)),
            "rmse_clim": math.sqrt(ec_sq / (n * 24))}


def report(name: str, days) -> None:
    print(f"\n### {name} — {len(days)} complete-24h days "
          f"({days[0][0]} … {days[-1][0]})")
    a = acf_lag1(days)
    print(f"  ACF(lag 1h)                 = {a:+.3f}   (claim +0.94)")
    s = persistence_sigma(days)
    print(f"  persistence shape corr S    = {s['s_obs']:+.3f}  "
          f"(null {s['null_mu']:+.3f} ± {s['null_sd']:.3f}, {s['n_pairs']} pairs)")
    print(f"  persistence vs shuffled null= {s['z']:.1f} sigma   (claim 12.8 sigma)")
    c = climatology_ratio(days)
    print(f"  climatology vs persistence (clim/persist, claim 'loses 2.2x'):")
    print(f"    level RMSE ratio          = {c['rmse_ratio']:.2f}x   "
          f"(persist {c['rmse_persist']:.1f} vs clim {c['rmse_clim']:.1f} EUR/MWh)")
    print(f"    level MSE (variance) ratio= {c['mse_ratio']:.2f}x")
    print(f"    level MAE ratio           = {c['mae_ratio']:.2f}x")
    print(f"    demeaned-SHAPE RMSE ratio = {c['shape_rmse_ratio']:.2f}x   "
          f"(<1 = climatology better)")
    print(f"    arbitrage capture         = persist {c['cap_persist']:.3f} "
          f"vs clim {c['cap_clim']:.3f}   (higher = better)")


def main() -> None:
    days = load_days()
    print(f"loaded {len(days)} complete-24h days from {DATA.name} "
          f"(dropped DST-irregular days)")
    # original ~182-day window ending at the probe date
    window = [dp for dp in days if PROBE_END - timedelta(days=PROBE_DAYS) < dp[0] <= PROBE_END]
    report(f"Founding window (~{PROBE_DAYS}d to {PROBE_END})", window)
    report("Full deep dataset (2015→2026)", days)


if __name__ == "__main__":
    main()
