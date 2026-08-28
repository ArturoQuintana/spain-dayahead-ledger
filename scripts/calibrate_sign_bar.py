"""One-time calibration of the autocorrelation-robust sign-test bar (Option C of
docs/multiple-comparisons-policy.md). Produces Data/calibration/sign_bar.json:
the moving-block-bootstrap null distribution of the win-count under H0 (no median
edge, autocorrelation preserved) for the climatology-vs-persistence delta series,
with a validity gate (KPSS stationarity + stability across windows).

Analysis-only, run ONCE and frozen. Uses numpy/statsmodels/arch (NOT wired into
the loop; compare_strategies.py only READS the frozen JSON, stdlib). Run:
  uv run --with numpy --with statsmodels --with arch python scripts/calibrate_sign_bar.py

The live strategy functions build the delta series, so the null matches
production. Deterministic (seeded).
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from arch.bootstrap import optimal_block_length
from statsmodels.tsa.stattools import kpss

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from esios_paper.loop import (climatology_basis, day_profile,  # noqa: E402
                              persistence_basis, pick_hours, pnl_eur)

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "Data" / "esios_prices.json"
OUT = ROOT / "Data" / "calibration" / "sign_bar.json"
CAL_DATE = date(2026, 8, 23)          # dataset end = calibration "as of" date
N_MIN, N_MAX = 30, 90
B = 10_000
TIE_EPS = 0.01
SEED = 0


def load_prices() -> dict[str, float]:
    prices = {}
    for rec in json.loads(DEEP.read_text()):
        if len(rec["prices"]) != 24:
            continue
        d, m, y = rec["date"].split("/")
        iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        for h, p in enumerate(rec["prices"]):
            prices[f"{iso}T{h:02d}"] = float(p)
    return prices


def daily_deltas(prices) -> list[tuple[date, float]]:
    """delta_T = pnl(climatology) - pnl(persistence) settled on day T, using the
    exact live basis functions. Only days where both bases exist and the target
    is a complete 24h day with all picked hours present."""
    days = sorted({k[:10] for k in prices})
    out = []
    for iso in days:
        target = date.fromisoformat(iso)
        actual = day_profile(prices, target)
        if len(actual) < 23:
            continue
        basis_day = target - timedelta(days=1)
        pb, _ = persistence_basis(prices, basis_day)
        cb, _ = climatology_basis(prices, basis_day)
        if pb is None or cb is None:
            continue
        pbuy, psell = pick_hours(pb)
        cbuy, csell = pick_hours(cb)
        if not all(h in actual for h in pbuy + psell + cbuy + csell):
            continue
        d = pnl_eur(cbuy, csell, actual) - pnl_eur(pbuy, psell, actual)
        out.append((target, round(d, 2)))
    return out


def signs_under_null(deltas: list[float]) -> np.ndarray:
    """Centre to impose H0 (median 0), drop ties (|round|<0.01), return +/-1."""
    arr = np.array(deltas, float)
    centred = arr - np.median(arr)
    nontied = centred[np.abs(np.round(centred, 2)) >= TIE_EPS]
    return np.sign(nontied).astype(int)


def block_bootstrap_survivals(signs, ell, rng):
    """Moving (circular) block bootstrap. One length-N_MAX sample per replicate;
    cumulative wins give every n in [N_MIN, N_MAX] consistently. Returns
    {n: [P(W>=w) for w in 0..n]}."""
    L = len(signs)
    nblocks = int(np.ceil(N_MAX / ell))
    starts = rng.integers(0, L, size=(B, nblocks))
    idx = (starts[:, :, None] + np.arange(ell)[None, None, :]) % L
    sample = signs[idx.reshape(B, -1)][:, :N_MAX]          # (B, N_MAX) of +/-1
    cumwins = np.cumsum(sample > 0, axis=1)                # (B, N_MAX)
    surv = {}
    for n in range(N_MIN, N_MAX + 1):
        wins = cumwins[:, n - 1]
        surv[n] = [float(np.mean(wins >= w)) for w in range(n + 1)]
    return surv


def w_star(surv_n) -> int:
    """Smallest win-count with survival <= 0.05 (the one-sided .95 critical value)."""
    for w, p in enumerate(surv_n):
        if p <= 0.05:
            return w
    return len(surv_n)


def kpss_p(x) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(kpss(x, regression="c", nlags="auto")[1])


def main() -> int:
    prices = load_prices()
    deltas = daily_deltas(prices)
    print(f"delta series: {len(deltas)} days, {deltas[0][0]} … {deltas[-1][0]}")
    rng = np.random.default_rng(SEED)

    windows = {
        "recent_24mo": [d for t, d in deltas if t > CAL_DATE - timedelta(days=730)],
        "crisis_excluded": [d for t, d in deltas
                            if not (date(2021, 1, 1) <= t <= date(2022, 12, 31))],
        "full": [d for _, d in deltas],
    }
    per_window = {}
    for name, ds in windows.items():
        s = signs_under_null(ds)
        cont = np.array(ds, float) - np.median(ds)           # for KPSS / block len
        p_kpss = kpss_p(cont)
        ell = float(optimal_block_length(cont)["circular"].iloc[0])
        ell = max(1, int(round(ell)))
        surv = block_bootstrap_survivals(s, ell, rng)
        per_window[name] = {"n_days": len(ds), "n_nontied": int(len(s)),
                            "kpss_p": p_kpss, "block_len": ell, "surv": surv,
                            "w_star_30": w_star(surv[30])}
        print(f"  {name:16} days={len(ds):5} nontied={len(s):5} "
              f"KPSS_p={p_kpss:.3f} ell={ell:2} w*(30)={w_star(surv[30])}")

    # validity gate: recent window stationary (KPSS can't reject) AND w*(30)
    # stable (within +/-2) across windows
    w30 = [per_window[w]["w_star_30"] for w in windows]
    stationary = per_window["recent_24mo"]["kpss_p"] >= 0.05
    stable = (max(w30) - min(w30)) <= 2
    valid = bool(stationary and stable)
    print(f"gate: stationary(recent KPSS_p>=0.05)={stationary} "
          f"stable(w*(30) range {max(w30)-min(w30)}<=2)={stable} -> VALID={valid}")

    # frozen survival = pointwise MAX across windows (most conservative)
    frozen = {}
    for n in range(N_MIN, N_MAX + 1):
        cols = [per_window[w]["surv"][n] for w in windows]
        frozen[str(n)] = [max(c[w] for c in cols) for w in range(n + 1)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "policy": "docs/multiple-comparisons-policy.md Option C",
        "reference_pair": ["battery-2h2h-climatology", "battery-2h2h-persistence"],
        "calibration_date": CAL_DATE.isoformat(),
        "n_replicates": B, "seed": SEED, "tie_eps": TIE_EPS,
        "valid": valid,
        "gate": {"stationary": stationary, "stable": stable,
                 "kpss_p_recent": per_window["recent_24mo"]["kpss_p"],
                 "w_star_30_by_window": {w: per_window[w]["w_star_30"] for w in windows}},
        "block_len_by_window": {w: per_window[w]["block_len"] for w in windows},
        "fallback": "Option A (p_iid<0.01, n>=45) if valid=false",
        "survival": frozen,       # survival[str(n)][w] = P(W>=w | H0, autocorr)
    }, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)} (valid={valid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
