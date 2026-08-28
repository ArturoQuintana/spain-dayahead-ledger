"""Tests for the weekly benchmark-note renderer.

The load-bearing guarantee: the note can NEVER print a superiority claim below
the pre-registered bar. That is enforced by comparison_line reusing the Option C
panel verdict AND additionally gating on pooled capture — so the tests exercise
(a) the no-bar-met wording, (b) a genuine bar-met, and critically (c) a
sign-significant-but-capture-failing strategy, which must NOT be called a winner.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import render_benchmark_note as r  # noqa: E402

PERS = "battery-2h2h-persistence"
CLIM = "battery-2h2h-climatology"
CAL_ON = {"valid": True, "survival": {}}   # calibrated regime, no survival table


def _ledger(tmp_path: Path, rows: list[dict], name="ledger.jsonl") -> Path:
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    return p


def _row(target, strat, pnl, oracle=None, capture=None):
    d = {"target": target, "strategy": strat, "pnl_eur": pnl}
    if oracle is not None:
        d["oracle_pnl_eur"] = oracle
    if capture is not None:
        d["capture"] = capture
    return d


def _market(ledger_path, currency="EUR", title="Test market", tab="Test"):
    return SimpleNamespace(slug="test", currency=currency, ledger_path=ledger_path,
                           receipts_path=ledger_path.with_name("receipts.jsonl"),
                           presentation=SimpleNamespace(title=title, tab_name=tab))


# --- small pure helpers ---

def test_window_bounds():
    assert r.window_bounds(date(2026, 8, 28), 7) == ("2026-08-22", "2026-08-28")
    assert r.window_bounds(date(2026, 8, 28), 1) == ("2026-08-28", "2026-08-28")


def test_load_settled_skips_blank_and_unsettled(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text(json.dumps(_row("2026-08-01", PERS, 5.0)) + "\n\n"
                 + json.dumps({"target": "2026-08-02", "strategy": PERS}) + "\n")  # open, no pnl
    rows = r.load_settled(p)
    assert len(rows) == 1 and rows[0]["target"] == "2026-08-01"


def test_load_settled_missing_file(tmp_path):
    assert r.load_settled(tmp_path / "nope.jsonl") == []


def test_summarize_capture_mean_and_positives():
    rows = [_row("2026-08-01", PERS, 100.0, capture=0.90),
            _row("2026-08-02", PERS, -10.0, capture=0.80),
            _row("2026-08-03", PERS, 50.0)]  # no capture on this day
    s = r.summarize(rows)[PERS]
    assert s["n"] == 3 and s["wins"] == 2
    assert abs(s["mean_pnl"] - 140.0 / 3) < 1e-9
    assert abs(s["capture"] - 0.85) < 1e-9   # mean of the two present captures


def test_summarize_capture_none_when_absent():
    assert r.summarize([_row("2026-08-01", PERS, 1.0)])[PERS]["capture"] is None


def test_fmt_money_currencies():
    assert r.fmt_money(1234.5, "EUR") == "€1,234.50"
    assert r.fmt_money(1234.5, "USD") == "$1,234.50"
    assert r.fmt_money(1234.5, "GBP") == "1,234.50 GBP"   # unknown -> code suffix


def test_cap_str():
    assert r._cap_str(0.972) == "97.2%"
    assert r._cap_str(None) == "—"


# --- market section ---

def test_market_section_orders_by_capture_and_labels_baseline(tmp_path):
    rows = [_row("2026-08-28", PERS, 100.0, capture=0.90),
            _row("2026-08-28", CLIM, 110.0, capture=0.97)]
    m = _market(_ledger(tmp_path, rows))
    md, n = r.render_market_section(m, date(2026, 8, 28), 7)
    assert n == 1
    # climatology (higher capture) appears before persistence
    assert md.index("climatology") < md.index("persistence")
    assert "persistence *(baseline)*" in md
    assert "97.0%" in md and "€100.00" in md


def test_market_section_empty_window_returns_zero(tmp_path):
    rows = [_row("2026-07-01", PERS, 100.0, capture=0.9)]   # outside the window
    m = _market(_ledger(tmp_path, rows))
    md, n = r.render_market_section(m, date(2026, 8, 28), 7)
    assert md == "" and n == 0


def test_market_section_usd_header(tmp_path):
    rows = [_row("2026-08-28", PERS, 200.0, capture=0.98)]
    m = _market(_ledger(tmp_path, rows), currency="USD")
    md, _ = r.render_market_section(m, date(2026, 8, 28), 7)
    assert "Mean $/day" in md and "$200.00" in md


# --- the standing line: the anti-over-claim guarantee ---

def test_comparison_line_no_bar_met_wording():
    rows = []
    for i in range(5):                       # only 5 days -> ineligible (n<30)
        t = f"2026-08-0{i + 1}"
        rows.append(_row(t, PERS, 100.0, oracle=200.0))
        rows.append(_row(t, CLIM, 110.0 if i < 3 else 90.0, oracle=200.0))
    line = r.comparison_line(rows, CAL_ON)
    assert line.startswith("No strategy has met the pre-registered bar")
    assert "confirmatory comparison: 5 shared non-tied days" in line


def test_comparison_line_bar_met_when_significant_and_capture_wins():
    rows = []
    for i in range(35):                      # 35 days, climatology wins every day
        t = f"2026-08-{i + 1:02d}"
        rows.append(_row(t, PERS, 100.0, oracle=200.0))    # capture 0.50
        rows.append(_row(t, CLIM, 150.0, oracle=200.0))    # capture 0.75, +50/day
    line = r.comparison_line(rows, CAL_ON)
    assert "has met the full pre-registered bar" in line
    assert "climatology" in line and "capture 75.0% vs 50.0%" in line


def test_comparison_line_capture_guard_blocks_significant_but_lower_capture():
    # Climatology WINS the sign test (25 tiny wins vs 5 big losses) but its pooled
    # capture is far BELOW persistence — the note must NOT call it a winner.
    rows = []
    for i in range(30):
        t = f"2026-08-{i + 1:02d}"
        rows.append(_row(t, PERS, 100.0, oracle=200.0))
        rows.append(_row(t, CLIM, 100.01 if i < 25 else -900.0, oracle=200.0))
    line = r.comparison_line(rows, CAL_ON)
    assert line.startswith("No strategy has met the pre-registered bar")


# --- whole note + CLI ---

def test_render_note_contains_fixed_sections_and_standing(tmp_path, monkeypatch):
    rows = [_row("2026-08-28", PERS, 100.0, oracle=110.0, capture=0.909),
            _row("2026-08-28", CLIM, 105.0, oracle=110.0, capture=0.955)]
    lp = _ledger(tmp_path, rows)
    prim = SimpleNamespace(slug="es", primary=True, currency="EUR", ledger_path=lp,
                           receipts_path=lp.with_name("receipts.jsonl"),
                           presentation=SimpleNamespace(title="Spain DA", tab_name="Spain"))
    monkeypatch.setattr(r, "MARKETS", {"es": prim})
    note = r.render_note(date(2026, 8, 28), 7, [prim], CAL_ON, mirror_url="example.test/ledger")
    assert "Committed-before-truth benchmark — week of 2026-08-28" in note
    assert "Spain DA" in note                       # market section
    assert "**Standing vs the baseline.**" in note
    assert "example.test/ledger" in note            # mirror url threaded
    assert "verify_ledger.py --all" in note         # verify block
    assert "no capital at risk" in note             # method footer
    assert "No strategy has met the pre-registered bar" in note


def test_render_note_footnotes_public_market_with_no_settled_days(tmp_path, monkeypatch):
    # A public market whose ledger has receipts but no settled days in the window
    # is listed in the "also live" footnote, not given a table.
    prim_rows = [_row("2026-08-28", PERS, 10.0, oracle=20.0, capture=0.5)]
    plp = _ledger(tmp_path, prim_rows, "prim.jsonl")
    prim = SimpleNamespace(slug="es", primary=True, currency="EUR", ledger_path=plp,
                           receipts_path=plp.with_name("receipts.jsonl"),
                           presentation=SimpleNamespace(title="Spain DA", tab_name="Spain"))
    # young market: empty ledger, but a receipts file exists
    young_lp = tmp_path / "young.jsonl"
    young_lp.write_text("")
    (tmp_path / "young_receipts.jsonl").write_text("{}\n")
    young = SimpleNamespace(slug="new", primary=False, currency="EUR", ledger_path=young_lp,
                            receipts_path=tmp_path / "young_receipts.jsonl",
                            presentation=SimpleNamespace(title="New DA", tab_name="Newland"))
    monkeypatch.setattr(r, "MARKETS", {"es": prim})
    note = r.render_note(date(2026, 8, 28), 7, [prim, young], CAL_ON)
    assert "ledgers opened" in note and "Newland" in note
    assert "New DA" not in note                      # no table for the young market


def test_main_writes_out_file(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "render_note", lambda *a, **k: "NOTE-BODY")
    monkeypatch.setattr(r, "public_markets", lambda: [])
    out = tmp_path / "note.md"
    rc = r.main(["--week-end", "2026-08-28", "--out", str(out)])
    assert rc == 0 and out.read_text() == "NOTE-BODY"


def test_main_defaults_week_end_to_market_today(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(r.loop, "market_today", lambda: date(2026, 8, 28))
    monkeypatch.setattr(r, "public_markets", lambda: [])
    monkeypatch.setattr(r, "render_note",
                        lambda we, *a, **k: seen.setdefault("we", we) and "" or "X")
    rc = r.main([])
    assert rc == 0 and seen["we"] == date(2026, 8, 28)
    assert capsys.readouterr().out == "X"
