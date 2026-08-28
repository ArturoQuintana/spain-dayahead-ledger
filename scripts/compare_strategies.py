"""The pre-registered strategy comparison (CLAUDE.md § Deciding strategy
comparisons + docs/multiple-comparisons-policy.md, Option C, ratified
2026-08-27). One-sided sign test on paired daily P&L deltas over shared settled
days, made robust to two hazards:

- MULTIPLICITY: one confirmatory comparison (climatology vs persistence, the
  a-priori hypothesis) at alpha; every other decision comparison is a Holm
  family.
- AUTOCORRELATION: the per-comparison p is p_eff = max(p_iid, p_boot), where
  p_boot is the frozen moving-block-bootstrap p (Data/calibration/sign_bar.json).
  The max floors it so the calibration can only harden the bar. If the
  calibration failed its validity gate, the blunt fallback (Option A: p_iid,
  alpha=0.01, n>=45) applies.

stdlib only: this reads the FROZEN calibration; producing it needs
scripts/calibrate_sign_bar.py (numpy/statsmodels/arch), run once.

Run: uv run python scripts/compare_strategies.py [a] [b]     # one comparison
     uv run python scripts/compare_strategies.py --panel      # full R1/R7 verdict
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "Data" / "es" / "ledger.jsonl"   # ES ledger (Data/es/ since Stage B)
CALIBRATION = ROOT / "Data" / "calibration" / "sign_bar.json"
TIE_EPS = 0.01
PRIMARY = "battery-2h2h-persistence"
# The single a-priori confirmatory comparison (registered 2026-08-01), exempt
# from the Holm family. Everything else is exploratory.
CONFIRMATORY = ("battery-2h2h-climatology", "battery-2h2h-persistence")


def sign_test_p(wins: int, n: int) -> float:
    """One-sided binomial P(X >= wins | n, 0.5) — the iid sign test (p_iid)."""
    return sum(comb(n, i) for i in range(wins, n + 1)) / 2 ** n


def load_calibration() -> dict | None:
    return json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else None


def mode(cal: dict | None) -> dict:
    """Option C selects between the calibrated regime and the Option-A fallback."""
    if cal and cal.get("valid"):
        return {"calibrated": True, "alpha": 0.05, "n_min": 30, "label": "calibrated"}
    return {"calibrated": False, "alpha": 0.01, "n_min": 45, "label": "fallback-A"}


def p_effective(cal: dict | None, m: dict, wins: int, n: int) -> tuple[float, str]:
    """p_eff = max(p_iid, p_boot) in the calibrated regime (iid-floored so the
    calibration can only harden); p_iid alone in the fallback."""
    p_iid = sign_test_p(wins, n)
    surv = (cal or {}).get("survival", {})
    if m["calibrated"] and str(n) in surv and 0 <= wins < len(surv[str(n)]):
        p_boot = surv[str(n)][wins]
        return (max(p_iid, p_boot), "p_boot" if p_boot >= p_iid else "p_iid-floor")
    return p_iid, "p_iid"


def evaluate(rows: list[dict], a: str, b: str) -> dict:
    """Pair A vs B on shared settled days; count non-tied wins/losses (deltas
    rounded to the 2-decimal P&L domain, |delta| < 0.01 excluded per rule A)."""
    by_day: dict[str, dict[str, float]] = {}
    cap: dict[str, dict[str, float]] = {}
    for r in rows:
        by_day.setdefault(r["target"], {})[r["strategy"]] = r["pnl_eur"]
        if r.get("oracle_pnl_eur"):
            cap.setdefault(r["strategy"], {})[r["target"]] = r["oracle_pnl_eur"]
    deltas = [(d, round(v[a] - v[b], 2)) for d, v in sorted(by_day.items())
              if a in v and b in v]
    wins = sum(1 for _, x in deltas if x >= TIE_EPS)
    losses = sum(1 for _, x in deltas if x <= -TIE_EPS)
    shared_days = [d for d, v in by_day.items() if a in v and b in v]
    pooled = _pooled_capture(by_day, cap, a, shared_days)
    pooled_b = _pooled_capture(by_day, cap, b, shared_days)
    return {"a": a, "b": b, "shared": len(deltas), "wins": wins, "losses": losses,
            "ties": len(deltas) - wins - losses, "n": wins + losses,
            "total": sum(x for _, x in deltas),
            "pooled_capture_a": pooled, "pooled_capture_b": pooled_b}


def _pooled_capture(by_day, cap, s, shared_days) -> float | None:
    num = den = 0.0
    for d in shared_days:
        if s in cap and d in cap[s] and cap[s][d]:
            num += by_day[d][s]; den += cap[s][d]
    return num / den if den else None


def panel_verdict(rows: list[dict], cal: dict | None) -> dict:
    """Apply Option C to the whole panel vs the primary: the confirmatory
    comparison standalone at alpha; the exploratory shadows as a Holm family.
    'significant' is the sign-test half of the R1/R7 bar (capture is separate)."""
    m = mode(cal)
    strategies = sorted({r["strategy"] for r in rows} - {PRIMARY})
    res = []
    for s in strategies:
        e = evaluate(rows, s, PRIMARY)
        peff, kind = p_effective(cal, m, e["wins"], e["n"])
        res.append({**e, "strategy": s, "p_eff": peff, "p_kind": kind,
                    "eligible": e["n"] >= m["n_min"],
                    "confirmatory": (s, PRIMARY) == CONFIRMATORY or
                                    (PRIMARY, s) == CONFIRMATORY})
    # confirmatory: standalone at alpha
    for r in res:
        if r["confirmatory"]:
            r["significant"] = r["eligible"] and r["p_eff"] < m["alpha"]
    # exploratory: Holm step-down among the eligible
    expl = sorted((r for r in res if not r["confirmatory"] and r["eligible"]),
                  key=lambda r: r["p_eff"])
    k = len(expl)
    for r in res:
        if not r["confirmatory"]:
            r["significant"] = False
    stopped = False
    for j, r in enumerate(expl):
        if not stopped and r["p_eff"] <= m["alpha"] / (k - j):
            r["significant"] = True
        else:
            stopped = True
    return {"mode": m, "comparisons": res}


def main() -> int:
    cal = load_calibration()
    m = mode(cal)
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]

    if "--panel" in sys.argv[1:]:
        v = panel_verdict(rows, cal)
        print(f"Panel vs {PRIMARY} | mode={m['label']} (alpha={m['alpha']}, "
              f"n>={m['n_min']})")
        for r in sorted(v["comparisons"], key=lambda r: r["p_eff"]):
            tag = "CONFIRMATORY" if r["confirmatory"] else "exploratory"
            verdict = ("BEATS PRIMARY (sign test)" if r["significant"]
                       else "not significant")
            print(f"  {r['strategy'].replace('battery-2h2h-',''):12} {tag:12} "
                  f"n={r['n']:2} wins={r['wins']:2} p_eff={r['p_eff']:.4f} "
                  f"({r['p_kind']}) -> {verdict}")
        return 0

    a = sys.argv[1] if len(sys.argv) > 1 else CONFIRMATORY[0]
    b = sys.argv[2] if len(sys.argv) > 2 else CONFIRMATORY[1]
    e = evaluate(rows, a, b)
    if not e["shared"]:
        print(f"no shared settled days between {a} and {b}")
        return 1
    peff, kind = p_effective(cal, m, e["wins"], e["n"])
    print(f"{a}  vs  {b}   [mode: {m['label']}]")
    print(f"shared settled days: {e['shared']} ({e['wins']} wins, {e['losses']} "
          f"losses, {e['ties']} ties) | total delta {e['total']:+.2f} EUR")
    if e["n"] == 0:
        print("verdict: all ties — no evidence either way")
        return 0
    print(f"p_iid = {sign_test_p(e['wins'], e['n']):.4f} | p_eff = {peff:.4f} "
          f"({kind}) on n = {e['n']}")
    confirmatory = (a, b) == CONFIRMATORY or (b, a) == CONFIRMATORY
    if confirmatory and e["n"] >= m["n_min"] and peff < m["alpha"]:
        print(f"verdict: CONFIRMATORY BAR MET — {a} beats {b}")
    elif confirmatory:
        print(f"verdict: bar NOT met (confirmatory needs n>={m['n_min']} and "
              f"p_eff<{m['alpha']}; have n={e['n']}, p_eff={peff:.3f})")
    else:
        print(f"verdict: exploratory — decided only in --panel (Holm family); "
              f"p_eff={peff:.3f}, n={e['n']} (need n>={m['n_min']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
