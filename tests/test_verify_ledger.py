"""The independent verifier must PASS on a faithful ledger and FAIL on a
tampered one — a re-derivation that cannot fail proves nothing. Each test
mutates one thing a real bug (or bad actor) would and asserts detection."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

# Load scripts/verify_ledger.py directly (it's a script, not a package module).
_SPEC = importlib.util.spec_from_file_location(
    "verify_ledger", Path(__file__).resolve().parents[1] / "scripts" / "verify_ledger.py")
vl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vl)

PARAMS = {"power_mw": 1.0, "rt_eff": 0.85, "fee_eur_mwh": 0.5}
TARGET, BASIS = "2026-01-02", "2026-01-01"


def _day_prices():
    # 24 distinct hourly prices; cheapest hours 0,1 / dearest 22,23.
    return [{"ts": f"{TARGET}T{h:02d}:00:00", "price": 100.0 + h} for h in range(24)]


def _write(base: Path, receipts, ledger, prices=None):
    (base / "prices.json").write_text(json.dumps(prices or _day_prices()))
    (base / "receipts.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in receipts))
    (base / "ledger.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in ledger))


def _faithful(base: Path):
    """A receipt + its correctly-derived settlement (buy off-oracle so capture<1)."""
    actual = {h: 100.0 + h for h in range(24)}
    buy, sell = [5, 6], [22, 23]
    rec = {"target": TARGET, "basis_day": BASIS, "buy_hours": buy,
           "sell_hours": sell, "strategy": "battery-2h2h-persistence",
           "strategy_version": "1", "params": PARAMS,
           "committed_at": f"{BASIS}T09:00:00+00:00"}
    ob, os_ = vl.pick_extremes(actual, 2)
    p = vl.pnl(buy, sell, actual, PARAMS)
    orc = vl.pnl(ob, os_, actual, PARAMS)
    entry = {"target": TARGET, "strategy": rec["strategy"],
             "strategy_version": "1", "buy_hours": buy, "sell_hours": sell,
             "buy_prices": [actual[h] for h in buy],
             "sell_prices": [actual[h] for h in sell], "pnl_eur": p,
             "oracle_pnl_eur": orc, "capture": round(p / orc, 3)}
    _write(base, [rec], [entry])
    return rec, entry


@pytest.fixture
def market(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "DATA", tmp_path)
    return tmp_path


def test_faithful_ledger_passes(market):
    _faithful(market)
    rep = vl.verify_market("es", verify_ots=False)
    assert rep.fails == [], rep.fails
    assert rep.checked == 1


def test_tampered_pnl_is_caught(market):
    _, entry = _faithful(market)
    entry["pnl_eur"] = round(entry["pnl_eur"] + 5.0, 2)  # inflate reported P&L
    (market / "ledger.jsonl").write_text(json.dumps(entry) + "\n")
    rep = vl.verify_market("es", verify_ots=False)
    assert any("pnl re-derived" in f for f in rep.fails), rep.fails


def test_altered_hours_are_caught(market):
    _, entry = _faithful(market)
    entry["sell_hours"] = [21, 23]  # settle on hours the receipt never committed
    (market / "ledger.jsonl").write_text(json.dumps(entry) + "\n")
    rep = vl.verify_market("es", verify_ots=False)
    assert any("differ from the committed receipt" in f for f in rep.fails), rep.fails


def test_leak_committed_on_target_day_is_caught(market):
    rec, entry = _faithful(market)
    rec["committed_at"] = f"{TARGET}T09:00:00+00:00"  # committed ON the target day
    (market / "receipts.jsonl").write_text(json.dumps(rec) + "\n")
    rep = vl.verify_market("es", verify_ots=False)
    assert any("LEAK" in f for f in rep.fails), rep.fails


def test_orphan_settlement_is_caught(market):
    _, entry = _faithful(market)
    (market / "receipts.jsonl").write_text("")  # settlement with no receipt behind it
    rep = vl.verify_market("es", verify_ots=False)
    assert any("orphan settlement" in f for f in rep.fails), rep.fails


def test_rewritten_history_breaks_ots_coverage(market):
    rec, entry = _faithful(market)
    ots = market / "ots"
    ots.mkdir()
    # An anchored manifest whose recorded hash matches NO prefix of the file =
    # the append-only trail was rewritten after anchoring.
    (ots / "2026-01-01.txt").write_text(
        "esios-paper audit manifest 2026-01-01\n"
        f"sha256(receipts.jsonl)={hashlib.sha256(b'a different history').hexdigest()}\n"
        "sha256(ledger.jsonl)=absent\n")
    (ots / "2026-01-01.txt.ots").write_bytes(b"\x00fake-proof")
    rep = vl.verify_market("es", verify_ots=False)
    assert any("matches NO prefix" in f for f in rep.fails), rep.fails


def test_valid_ots_prefix_is_covered(market):
    _faithful(market)
    ots = market / "ots"
    ots.mkdir()
    digest = hashlib.sha256((market / "receipts.jsonl").read_bytes()).hexdigest()
    (ots / "2026-01-02.txt").write_text(
        "esios-paper audit manifest 2026-01-02\n"
        f"sha256(receipts.jsonl)={digest}\n"
        "sha256(ledger.jsonl)=absent\n")
    (ots / "2026-01-02.txt.ots").write_bytes(b"\x00proof")
    rep = vl.verify_market("es", verify_ots=False)
    assert rep.fails == [], rep.fails
    assert any("Bitcoin-covered 1/1" in m for m in rep.info), rep.info
