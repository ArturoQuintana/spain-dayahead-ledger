"""The strategy comparison decides R1 promotion / R7 retirement, so its Option-C
boundary must be pinned exactly: the binomial p_iid, the calibration floor
(p_eff = max(p_iid, p_boot)), the confirmatory-vs-Holm split, and the
fallback regime when the calibration is invalid. Failure-mode-first: most cases
assert a decision is NOT reached on inputs a naive reading would pass."""
import importlib.util
import json
from math import comb
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "compare_strategies",
    Path(__file__).resolve().parents[1] / "scripts" / "compare_strategies.py")
cs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cs)

CLIM, PERS = "battery-2h2h-climatology", "battery-2h2h-persistence"
RANK, WEEK = "battery-2h2h-rankblend", "battery-2h2h-weekly"


def surv(n, overrides=None):
    a = [cs.sign_test_p(w, n) for w in range(n + 1)]   # iid baseline (harmless)
    for w, p in (overrides or {}).items():
        a[w] = p
    return a


def cal_valid(survivals):
    return {"valid": True, "survival": {str(n): s for n, s in survivals.items()}}


def rows(pairs):
    """pairs: (day, strategy, pnl[, oracle])."""
    out = []
    for p in pairs:
        r = {"target": p[0], "strategy": p[1], "pnl_eur": p[2]}
        if len(p) > 3:
            r["oracle_pnl_eur"] = p[3]
        out.append(r)
    return out


def head_to_head(a, b, wins, losses, day0=1):
    out = []
    for i in range(wins):
        out += [(f"d{day0+i:03d}", a, 10.0), (f"d{day0+i:03d}", b, 0.0)]
    for i in range(losses):
        out += [(f"e{day0+i:03d}", a, 0.0), (f"e{day0+i:03d}", b, 10.0)]
    return out


# ---- the binomial core -------------------------------------------------------

def test_sign_test_p_known_values():
    assert cs.sign_test_p(1, 1) == 0.5
    assert cs.sign_test_p(0, 1) == 1.0
    assert cs.sign_test_p(2, 2) == 0.25
    assert cs.sign_test_p(30, 30) == 1 / 2 ** 30


# ---- evaluate: pairing + tie handling ----------------------------------------

def test_only_shared_days_paired_and_tie_boundary():
    ev = cs.evaluate(rows([
        ("d1", CLIM, 1.00), ("d1", PERS, 0.99),   # +0.01 -> win (rule A)
        ("d2", CLIM, 1.00), ("d2", PERS, 1.00),   # 0.00 -> tie
        ("d3", CLIM, 1.00),                        # PERS absent -> excluded
    ]), CLIM, PERS)
    assert ev["shared"] == 2 and ev["wins"] == 1 and ev["ties"] == 1 and ev["n"] == 1


def test_pooled_capture_computed_when_oracle_present():
    ev = cs.evaluate(rows([
        ("d1", CLIM, 90.0, 100.0), ("d1", PERS, 80.0, 100.0)]), CLIM, PERS)
    assert ev["pooled_capture_a"] == pytest.approx(0.9)
    assert ev["pooled_capture_b"] == pytest.approx(0.8)


# ---- mode selection ----------------------------------------------------------

def test_valid_calibration_is_calibrated_mode():
    m = cs.mode({"valid": True, "survival": {}})
    assert m["calibrated"] and m["alpha"] == 0.05 and m["n_min"] == 30


def test_invalid_or_missing_calibration_is_fallback_A():
    for cal in ({"valid": False}, None):
        m = cs.mode(cal)
        assert not m["calibrated"] and m["alpha"] == 0.01 and m["n_min"] == 45


# ---- p_eff = max(p_iid, p_boot): the floor -----------------------------------

def test_calibration_can_only_harden_the_bar():
    # 28/30 wins: p_iid is tiny; the calibration says p_boot=0.03 -> p_eff hardens
    cal = cal_valid({30: surv(30, {28: 0.03})})
    peff, kind = cs.p_effective(cal, cs.mode(cal), wins=28, n=30)
    assert peff == 0.03 and kind == "p_boot"
    assert peff > cs.sign_test_p(28, 30)          # strictly harder than iid


def test_iid_floor_protects_when_calibration_says_too_easy():
    # p_boot understates (0.001) but p_iid at 20/30 ~ 0.049 -> floor wins
    cal = cal_valid({30: surv(30, {20: 0.001})})
    peff, kind = cs.p_effective(cal, cs.mode(cal), wins=20, n=30)
    assert peff == pytest.approx(cs.sign_test_p(20, 30)) and kind == "p_iid-floor"


def test_fallback_uses_iid_only():
    peff, kind = cs.p_effective(None, cs.mode(None), wins=28, n=45)
    assert peff == cs.sign_test_p(28, 45) and kind == "p_iid"


# ---- panel_verdict: confirmatory standalone + Holm family --------------------

def test_confirmatory_beats_primary_at_alpha_without_holm():
    # climatology wins 30/0 -> p_iid tiny; calibration harmless -> significant
    cal = cal_valid({30: surv(30, {})})
    v = cs.panel_verdict(rows(head_to_head(CLIM, PERS, 30, 0)), cal)
    clim = next(c for c in v["comparisons"] if c["strategy"] == CLIM)
    assert clim["confirmatory"] and clim["significant"]


def test_confirmatory_needs_n_min():
    cal = cal_valid({})
    v = cs.panel_verdict(rows(head_to_head(CLIM, PERS, 29, 0)), cal)   # n=29 < 30
    clim = next(c for c in v["comparisons"] if c["strategy"] == CLIM)
    assert not clim["eligible"] and not clim["significant"]


def test_exploratory_holm_tightens_with_family_size():
    # rankblend alone at p_eff = 0.04: family k=1 -> threshold 0.05 -> significant
    cal = cal_valid({30: surv(30, {25: 0.04})})
    solo = cs.panel_verdict(rows(head_to_head(RANK, PERS, 25, 5)), cal)
    assert next(c for c in solo["comparisons"] if c["strategy"] == RANK)["significant"]
    # add weekly ALSO at p_eff = 0.04: k=2 -> smallest needs <= 0.05/2 = 0.025 ->
    # the step-down fails at the first, so NEITHER is significant.
    two = cs.panel_verdict(rows(head_to_head(RANK, PERS, 25, 5) +
                                head_to_head(WEEK, PERS, 25, 5, day0=100)), cal)
    assert not any(c["significant"] for c in two["comparisons"]
                   if not c["confirmatory"])


def test_fallback_mode_raises_n_and_tightens_alpha():
    # 30/0 wins: n=30 < 45 fallback precondition -> not eligible, not significant
    v = cs.panel_verdict(rows(head_to_head(CLIM, PERS, 30, 0)), {"valid": False})
    clim = next(c for c in v["comparisons"] if c["strategy"] == CLIM)
    assert v["mode"]["label"] == "fallback-A" and not clim["eligible"]


# ---- main() CLI --------------------------------------------------------------

def _cli(monkeypatch, tmp_path, ledger, cal=None, argv=()):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(cs, "CALIBRATION", tmp_path / "cal.json")
    (tmp_path / "ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in ledger))
    if cal is not None:
        (tmp_path / "cal.json").write_text(json.dumps(cal))
    monkeypatch.setattr(cs.sys, "argv", ["compare_strategies.py", *argv])


def test_main_confirmatory_bar_met(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, rows(head_to_head(CLIM, PERS, 30, 0)),
         cal=cal_valid({30: surv(30, {})}), argv=(CLIM, PERS))
    assert cs.main() == 0
    assert "CONFIRMATORY BAR MET" in capsys.readouterr().out


def test_main_no_shared_days(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, rows([("d1", CLIM, 5.0)]), argv=(CLIM, PERS))
    assert cs.main() == 1
    assert "no shared settled days" in capsys.readouterr().out


def test_main_panel_mode(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, rows(head_to_head(CLIM, PERS, 30, 0)),
         cal=cal_valid({30: surv(30, {})}), argv=("--panel",))
    assert cs.main() == 0
    out = capsys.readouterr().out
    assert "Panel vs" in out and "CONFIRMATORY" in out


def test_main_all_ties(monkeypatch, tmp_path, capsys):
    led = rows([("d1", CLIM, 5.0), ("d1", PERS, 5.0),
                ("d2", CLIM, 7.0), ("d2", PERS, 7.0)])
    _cli(monkeypatch, tmp_path, led, argv=(CLIM, PERS))
    assert cs.main() == 0
    assert "all ties" in capsys.readouterr().out


def test_main_confirmatory_bar_not_met(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, rows(head_to_head(CLIM, PERS, 3, 2)),   # n=5
         cal=cal_valid({30: surv(30, {})}), argv=(CLIM, PERS))
    assert cs.main() == 0
    assert "bar NOT met" in capsys.readouterr().out


def test_main_exploratory_deferred_to_panel(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, rows(head_to_head(RANK, PERS, 20, 5)),
         cal=cal_valid({30: surv(30, {})}), argv=(RANK, PERS))
    assert cs.main() == 0
    assert "decided only in --panel" in capsys.readouterr().out
