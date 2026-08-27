"""The strategy comparison decides R1 promotion — a strategy can become PRIMARY
on its verdict — so its boundary must be pinned exactly. These tests target the
pre-registered bar (>=30 NON-TIED shared days AND one-sided sign-test p<0.05),
the tie epsilon, and the binomial math itself. Failure-mode-first: most cases
assert the bar is NOT met on inputs a naive reading would pass."""
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

A, B = "stratA", "stratB"


def rows_from(pairs):
    """pairs: list of (day, pnl_a, pnl_b). None pnl = that strategy absent that
    day (tests shared-day pairing)."""
    out = []
    for day, pa, pb in pairs:
        if pa is not None:
            out.append({"target": day, "strategy": A, "pnl_eur": pa})
        if pb is not None:
            out.append({"target": day, "strategy": B, "pnl_eur": pb})
    return out


# ---- the binomial core -------------------------------------------------------

def test_sign_test_p_known_small_values():
    assert cs.sign_test_p(1, 1) == 0.5
    assert cs.sign_test_p(0, 1) == 1.0
    assert cs.sign_test_p(2, 2) == 0.25
    assert cs.sign_test_p(1, 2) == 0.75


def test_sign_test_p_extremes_and_monotonicity():
    for n in (5, 12, 30):
        assert cs.sign_test_p(0, n) == 1.0                 # X>=0 is certain
        assert cs.sign_test_p(n, n) == 1 / 2 ** n          # all wins
        # matches the explicit binomial tail
        assert cs.sign_test_p(n - 1, n) == (comb(n, n - 1) + comb(n, n)) / 2 ** n
    # strictly decreasing as required wins rise
    ps = [cs.sign_test_p(w, 30) for w in range(0, 31)]
    assert all(ps[i] > ps[i + 1] for i in range(len(ps) - 1))


# ---- pairing & tie handling --------------------------------------------------

def test_only_shared_days_are_paired():
    ev = cs.evaluate(rows_from([
        ("d1", 10.0, 5.0),      # shared
        ("d2", 10.0, None),     # A only — excluded
        ("d3", None, 5.0),      # B only — excluded
    ]), A, B)
    assert ev["shared"] == 1
    assert ev["deltas"] == [("d1", 5.0)]


def test_win_loss_tie_classification():
    ev = cs.evaluate(rows_from([
        ("d1", 1.00, 1.00),     # delta 0.00 -> tie
        ("d2", 1.02, 1.00),     # delta +0.02 -> win
        ("d3", 1.00, 1.02),     # delta -0.02 -> loss
        ("d4", 5.00, 3.00),     # delta +2.00 -> win
    ]), A, B)
    assert (ev["wins"], ev["losses"], ev["ties"]) == (2, 1, 1)
    assert ev["n"] == 3


def test_one_cent_delta_counts_and_is_float_deterministic():
    # Pre-registered rule A: |delta| < 0.01 is a tie, so a rounded +/-0.01
    # is a genuine directional difference and COUNTS. round() makes this
    # independent of float representation (1.00-0.99 == 0.010000000000000009).
    ev = cs.evaluate(rows_from([
        ("d1", 1.00, 0.99),     # +0.01 -> WIN (not a tie)
        ("d2", 1.00, 1.01),     # -0.01 -> LOSS
        ("d3", 5.00, 5.00),     # 0.00 -> tie (only exact equality)
    ]), A, B)
    assert (ev["wins"], ev["losses"], ev["ties"]) == (1, 1, 1)
    assert ev["n"] == 2


# ---- the pre-registered promotion boundary -----------------------------------

def test_bar_met_when_30_nontied_days_and_tiny_p():
    ev = cs.evaluate(rows_from([(f"d{i}", 10.0, 0.0) for i in range(30)]), A, B)
    assert ev["n"] == 30 and ev["wins"] == 30
    assert ev["p"] == 1 / 2 ** 30
    assert ev["bar_met"] is True


def test_29_nontied_days_never_meets_bar_even_with_p_zero():
    # The >=30 requirement is a hard gate independent of significance.
    ev = cs.evaluate(rows_from([(f"d{i}", 10.0, 0.0) for i in range(29)]), A, B)
    assert ev["n"] == 29
    assert ev["p"] == 1 / 2 ** 29         # overwhelmingly significant
    assert ev["bar_met"] is False


def test_ties_do_not_count_toward_the_30():
    # 34 shared days but 5 ties -> only 29 non-tied -> bar NOT met.
    pairs = [(f"w{i}", 10.0, 0.0) for i in range(29)] + \
            [(f"t{i}", 1.0, 1.0) for i in range(5)]
    ev = cs.evaluate(rows_from(pairs), A, B)
    assert ev["shared"] == 34 and ev["ties"] == 5 and ev["n"] == 29
    assert ev["bar_met"] is False
    # add one more clean win -> 30 non-tied -> now it meets the bar
    ev2 = cs.evaluate(rows_from(pairs + [("w29", 10.0, 0.0)]), A, B)
    assert ev2["n"] == 30 and ev2["bar_met"] is True


def test_30_days_but_insignificant_split_does_not_meet_bar():
    # 16 wins / 14 losses over n=30 -> p ~ 0.43 -> bar NOT met.
    pairs = [(f"w{i}", 10.0, 0.0) for i in range(16)] + \
            [(f"l{i}", 0.0, 10.0) for i in range(14)]
    ev = cs.evaluate(rows_from(pairs), A, B)
    assert ev["n"] == 30 and ev["wins"] == 16
    assert ev["p"] > 0.05
    assert ev["bar_met"] is False


def test_all_ties_gives_no_verdict():
    ev = cs.evaluate(rows_from([(f"d{i}", 1.0, 1.0) for i in range(40)]), A, B)
    assert ev["n"] == 0 and ev["p"] is None and ev["bar_met"] is False


def test_no_shared_days():
    ev = cs.evaluate(rows_from([("d1", 10.0, None), ("d2", None, 5.0)]), A, B)
    assert ev["deltas"] == [] and ev["bar_met"] is False


# ---- main() (CLI over a real ledger file) ------------------------------------

def _write_ledger(tmp_path, monkeypatch, rows, argv=("A", "B")):
    monkeypatch.setattr(cs, "LEDGER", tmp_path / "ledger.jsonl")
    (tmp_path / "ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(cs.sys, "argv", ["compare_strategies.py", *argv])


def test_main_no_shared_days_returns_one(monkeypatch, tmp_path, capsys):
    _write_ledger(monkeypatch=monkeypatch, tmp_path=tmp_path, rows=[
        {"target": "d1", "strategy": "A", "pnl_eur": 5.0}])   # B never appears
    assert cs.main() == 1
    assert "no shared settled days" in capsys.readouterr().out


def test_main_all_ties_reports_no_evidence(monkeypatch, tmp_path, capsys):
    rows = []
    for i in range(5):
        rows += [{"target": f"d{i}", "strategy": "A", "pnl_eur": 3.0},
                 {"target": f"d{i}", "strategy": "B", "pnl_eur": 3.0}]
    _write_ledger(monkeypatch=monkeypatch, tmp_path=tmp_path, rows=rows)
    assert cs.main() == 0
    assert "all ties" in capsys.readouterr().out


def test_main_bar_not_met(monkeypatch, tmp_path, capsys):
    rows = []
    for i in range(5):                              # only 5 non-tied days
        rows += [{"target": f"d{i}", "strategy": "A", "pnl_eur": 10.0},
                 {"target": f"d{i}", "strategy": "B", "pnl_eur": 0.0}]
    _write_ledger(monkeypatch=monkeypatch, tmp_path=tmp_path, rows=rows)
    assert cs.main() == 0
    out = capsys.readouterr().out
    assert "bar NOT met" in out and "n=5" in out


def test_main_bar_met_declares_winner(monkeypatch, tmp_path, capsys):
    rows = []
    for i in range(30):                             # 30 clean wins for A
        rows += [{"target": f"2026-08-{i:02d}", "strategy": "A", "pnl_eur": 10.0},
                 {"target": f"2026-08-{i:02d}", "strategy": "B", "pnl_eur": 0.0}]
    _write_ledger(monkeypatch=monkeypatch, tmp_path=tmp_path, rows=rows)
    assert cs.main() == 0
    assert "PRE-REGISTERED BAR MET" in capsys.readouterr().out
