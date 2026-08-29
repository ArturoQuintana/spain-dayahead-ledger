"""Coverage for the public dashboard renderer. It ships numbers to a public
page, so the contract is: every figure is computed correctly from the audit
files and lands in the HTML. We assert the Python-computed values (totals,
capture, wins, missed days, pair deltas, gate progress, market labels) — the
client-side SVG/JS is out of scope for unit tests. Failure-mode-first: the
missed-day and market-awareness cases are the ones a naive renderer gets wrong."""
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "render_dashboard",
    Path(__file__).resolve().parents[1] / "scripts" / "render_dashboard.py")
rd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rd)

P = "battery-2h2h-persistence"
C = "battery-2h2h-climatology"


def _prices(days):
    rows = []
    for d in days:
        for h in range(24):
            rows.append({"ts": f"{d}T{h:02d}", "price": 50.0 + h})
    return rows


def _settle(target, strat, pnl, oracle, cap, tau=0.9):
    return {"target": target, "strategy": strat, "strategy_version": "1",
            "buy_hours": [12, 13], "sell_hours": [21, 22],
            "buy_prices": [85.27, 83.27], "sell_prices": [175.44, 176.01],
            "pnl_eur": pnl, "oracle_pnl_eur": oracle, "capture": cap, "tau": tau}


def _receipt(target, basis, strat, committed="2026-08-12T09:04:00+00:00"):
    return {"target": target, "basis_day": basis, "strategy": strat,
            "strategy_version": "1", "buy_hours": [12, 13], "sell_hours": [21, 22],
            "committed_at": committed}


def _seed(monkeypatch, tmp_path, slug, days, ledger, receipts):
    d = tmp_path / slug
    d.mkdir(parents=True)
    (d / "prices.json").write_text(json.dumps(_prices(days)))
    (d / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ledger))
    (d / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    monkeypatch.setitem(rd.MARKETS[slug], "data", d)
    return d


# ---- helpers -----------------------------------------------------------------

def test_fmt_thousands_and_two_decimals():
    assert rd.fmt(1234.5) == "1,234.50"
    assert rd.fmt(-3.1) == "-3.10"


def test_jsonl_missing_file_is_empty(tmp_path):
    assert rd.jsonl(tmp_path / "nope.jsonl") == []


def test_day_curves_builds_24_slot_arrays(tmp_path):
    (tmp_path / "prices.json").write_text(json.dumps(_prices(["2026-08-13"])))
    curves = rd.day_curves(tmp_path)
    assert list(curves) == ["2026-08-13"]
    assert len(curves["2026-08-13"]) == 24 and curves["2026-08-13"][5] == 55.0


# ---- build(): the numbers on the page ----------------------------------------

def test_build_es_core_numbers_and_gate(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 128.34, 151.82, 0.845),
              _settle("2026-08-13", C, 130.00, 151.82, 0.856)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P),
                _receipt("2026-08-13", "2026-08-12", C),
                _receipt("2026-08-14", "2026-08-13", P)]      # open (unsettled)
    _seed(monkeypatch, tmp_path, "es", ["2026-08-12", "2026-08-13"], ledger, receipts)
    html = rd.build("es")
    assert "+128.34" in html                         # primary total
    assert "151.82" in html and "84.5" in html       # oracle ceiling, mean capture
    assert "1 / 1" in html                           # 1 win of 1 settled
    assert '"target": "2026-08-13"' in html          # day-card JSON present
    assert "over 1 shared days" in html              # climatology-vs-primary pair note
    assert "GBM v2 gate" in html and "1 / 21" in html  # ES-only gate tile
    assert "Escalation gate" in html
    # the open 2026-08-14 receipt renders a pending card
    assert "Pending" in html and "2026-08-14" in html


def test_build_counts_missed_days(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 100.0, 120.0, 0.83),
              _settle("2026-08-15", P, 90.0, 110.0, 0.82)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P),
                _receipt("2026-08-15", "2026-08-14", P)]      # 08-14 has NO receipt
    _seed(monkeypatch, tmp_path, "es",
          ["2026-08-12", "2026-08-13", "2026-08-14", "2026-08-15"], ledger, receipts)
    html = rd.build("es")
    assert "2 missed" not in html                    # exactly one gap
    assert "1 missed" in html or "· 1 missed" in html
    assert "missed — no receipt committed" in html   # the missed ledger row
    assert "2 / 2" in html                           # both settled days won


def test_build_no_open_receipts_shows_none(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 100.0, 120.0, 0.83)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]      # all settled
    _seed(monkeypatch, tmp_path, "es", ["2026-08-12", "2026-08-13"], ledger, receipts)
    html = rd.build("es")
    assert "None open" in html


def test_build_de_is_market_aware_without_gate(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 200.0, 210.0, 0.95)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    _seed(monkeypatch, tmp_path, "de", ["2026-08-12", "2026-08-13"], ledger, receipts)
    html = rd.build("de")
    assert "German (DE-LU) day-ahead battery arbitrage" in html
    assert "Germany day-ahead ledger" in html        # tab title
    assert "SMARD.de" in html                        # source line
    assert "Escalation gate" not in html             # gate is ES-only
    assert "silent shadow ledger" in html and ">DE<" in html


# ---- main(): file output -----------------------------------------------------

def test_main_writes_wrapped_html(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 100.0, 120.0, 0.83)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    _seed(monkeypatch, tmp_path, "es", ["2026-08-12", "2026-08-13"], ledger, receipts)
    out = tmp_path / "index.html"
    monkeypatch.setattr(rd.sys, "argv", ["render_dashboard.py", str(out)])
    rd.main()
    text = out.read_text()
    assert text.startswith("<!doctype html>") and text.rstrip().endswith("</html>")
    assert "Spanish day-ahead battery arbitrage" in text


def test_main_market_flag_selects_de(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 200.0, 210.0, 0.95)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    _seed(monkeypatch, tmp_path, "de", ["2026-08-12", "2026-08-13"], ledger, receipts)
    out = tmp_path / "de.html"
    monkeypatch.setattr(rd.sys, "argv", ["render_dashboard.py", "--market", "de", str(out)])
    rd.main()
    assert "German (DE-LU) day-ahead battery arbitrage" in out.read_text()


# ---- P1: one-project mirror (currency, awaiting, nav, ES-at-index) -----------

def test_currency_symbol_is_per_market(monkeypatch, tmp_path):
    """A GBP market renders £, never €. A public page showing the wrong currency
    would undermine the credibility the record exists to establish."""
    ledger = [_settle("2026-08-13", P, 100.0, 120.0, 0.83)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    _seed(monkeypatch, tmp_path, "gb", ["2026-08-12", "2026-08-13"], ledger, receipts)
    html = rd.build("gb")
    assert "£" in html and "€" not in html
    assert "Absolute GBP is an" in html


def test_awaiting_page_when_no_settled_day(monkeypatch, tmp_path):
    """A live market with committed receipts but no settled day renders the honest
    'awaiting first settled day' page — never a crash, never a fake +0.00."""
    receipts = [_receipt("2026-08-14", "2026-08-13", P)]
    _seed(monkeypatch, tmp_path, "gb", ["2026-08-13"], [], receipts)   # empty ledger
    html = rd.build("gb")
    assert "awaiting first settled day" in html
    assert "Pending" in html and "2026-08-14" in html
    assert "+0.00" not in html


def test_nav_links_all_markets_and_marks_current(monkeypatch):
    nav = rd._nav(["es", "de", "gb"], "de", "es")
    assert ">Talea<" in nav
    assert 'href="index.html"' in nav              # primary es -> index.html
    assert 'href="de.html" class="here"' in nav    # current market marked
    assert 'href="gb.html"' in nav


def test_main_site_es_is_index_others_are_siblings(monkeypatch, tmp_path):
    """--site keeps the primary (ES) at index.html (NOT demoted to es.html) and
    writes each other public market as a first-class sibling page, all carrying
    the Talea nav. One project, no market subordinated, no 'benchmark' hub."""
    _seed(monkeypatch, tmp_path, "es", ["2026-08-12", "2026-08-13"],
          [_settle("2026-08-13", P, 100.0, 120.0, 0.90)],
          [_receipt("2026-08-13", "2026-08-12", P)])
    _seed(monkeypatch, tmp_path, "de", ["2026-08-12", "2026-08-13"],
          [_settle("2026-08-13", P, 200.0, 210.0, 0.95)],
          [_receipt("2026-08-13", "2026-08-12", P)])
    fake = [type("M", (), {"slug": s})() for s in ("es", "de")]
    monkeypatch.setattr(rd, "_public_markets", lambda: fake)
    out = tmp_path / "site"
    monkeypatch.setattr(rd.sys, "argv", ["render_dashboard.py", "--site", str(out)])
    rd.main()
    assert (out / "index.html").exists()           # ES at the root
    assert not (out / "es.html").exists()          # ES not demoted
    assert (out / "de.html").exists()
    idx = (out / "index.html").read_text()
    assert 'class="talea-nav"' in idx and "Spanish day-ahead battery arbitrage" in idx
    assert "German (DE-LU) day-ahead battery arbitrage" in (out / "de.html").read_text()


def test_day_card_skipped_when_basis_curve_missing(monkeypatch, tmp_path):
    # basis day 2026-08-12 has NO price row -> the day card is dropped, but the
    # settlement still appears in the append-only ledger table.
    ledger = [_settle("2026-08-13", P, 128.34, 151.82, 0.845)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    _seed(monkeypatch, tmp_path, "es", ["2026-08-13"], ledger, receipts)  # 08-12 absent
    html = rd.build("es")
    assert '"target": "2026-08-13"' not in html     # no card (basis missing)
    assert "+128.34" in html                         # but the ledger row stands


def test_day_card_skipped_when_an_hour_is_missing(monkeypatch, tmp_path):
    ledger = [_settle("2026-08-13", P, 128.34, 151.82, 0.845)]
    receipts = [_receipt("2026-08-13", "2026-08-12", P)]
    d = _seed(monkeypatch, tmp_path, "es", ["2026-08-12", "2026-08-13"], ledger, receipts)
    # drop one hour from the target day so its curve has a None
    rows = [r for r in json.loads((d / "prices.json").read_text())
            if r["ts"] != "2026-08-13T05"]
    (d / "prices.json").write_text(json.dumps(rows))
    html = rd.build("es")
    assert '"target": "2026-08-13"' not in html      # incomplete curve -> skipped
