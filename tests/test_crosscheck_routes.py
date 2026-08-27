"""The two-route crosscheck is the ledger's last silent-corruption guard: it
compares the loop's dataset of record (route A, tokenless apidatos) against an
independent token route (route B) hour-by-hour. These tests pin that it AGREES
within tolerance, FAILS loudly on a real disagreement, is INCONCLUSIVE when
route B is stale, and never compares incomplete (DST) days. A large days_back
is passed so the trailing-window cutoff is deterministic."""
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "crosscheck_routes",
    Path(__file__).resolve().parents[1] / "scripts" / "crosscheck_routes.py")
cc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cc)

DAYS = ["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]


def _seed(monkeypatch, tmp_path, route_a, route_b, argv=("100000",)):
    """route_a/route_b: {day_iso: {hour: price}}. A missing hour in a day makes
    that day's list shorter than 24 (an incomplete/DST day)."""
    ra = [{"ts": f"{d}T{h:02d}", "price": p}
          for d, hrs in route_a.items() for h, p in sorted(hrs.items())]
    (tmp_path / "prices.json").write_text(json.dumps(ra))
    rb = [{"date": date.fromisoformat(d).strftime("%d/%m/%Y"),
           "prices": [hrs[h] for h in sorted(hrs)]}
          for d, hrs in route_b.items()]
    (tmp_path / "esios_prices.json").write_text(json.dumps(rb))
    monkeypatch.setattr(cc, "DATA", tmp_path)
    monkeypatch.setattr(cc.sys, "argv", ["crosscheck_routes.py", *argv])


def _full(base):
    return {d: {h: base + h for h in range(24)} for d in DAYS[:3]}


def test_routes_agree_returns_zero(monkeypatch, tmp_path, capsys):
    _seed(monkeypatch, tmp_path, _full(50.0), _full(50.0))
    assert cc.main() == 0
    assert "crosscheck ok: 3 days" in capsys.readouterr().out


def test_within_tolerance_still_agrees(monkeypatch, tmp_path, capsys):
    a = _full(50.0)
    b = {d: {h: v + 0.4 for h, v in hrs.items()} for d, hrs in a.items()}  # < 0.51
    _seed(monkeypatch, tmp_path, a, b)
    assert cc.main() == 0
    assert "agree within" in capsys.readouterr().out


def test_disagreement_beyond_tolerance_fails(monkeypatch, tmp_path, capsys):
    a = _full(50.0)
    b = _full(50.0)
    b["2026-08-12"][10] = 999.0                 # one broken hour
    _seed(monkeypatch, tmp_path, a, b)
    assert cc.main() == 1
    out = capsys.readouterr().out
    assert "CROSSCHECK FAILED" in out and "2026-08-12" in out


def test_custom_tolerance_argument_is_honored(monkeypatch, tmp_path, capsys):
    a = _full(50.0)
    b = {d: {h: v + 0.4 for h, v in hrs.items()} for d, hrs in a.items()}
    _seed(monkeypatch, tmp_path, a, b, argv=("100000", "0.3"))   # 0.4 > 0.3
    assert cc.main() == 1
    assert "CROSSCHECK FAILED" in capsys.readouterr().out


def test_inconclusive_when_too_few_shared_days(monkeypatch, tmp_path, capsys):
    two = {d: {h: 50.0 + h for h in range(24)} for d in DAYS[:2]}
    _seed(monkeypatch, tmp_path, two, two)
    assert cc.main() == 1
    assert "CROSSCHECK INCONCLUSIVE" in capsys.readouterr().out


def test_incomplete_day_is_excluded_from_comparison(monkeypatch, tmp_path, capsys):
    # 3 complete matching days + a 4th day that DISAGREES but is incomplete in
    # route A (23 hours) -> excluded, so the result is still "ok".
    a = _full(50.0)
    b = _full(50.0)
    a["2026-08-14"] = {h: 50.0 + h for h in range(24) if h != 5}   # 23 hours
    b["2026-08-14"] = {h: 9999.0 for h in range(24)}               # would fail if compared
    _seed(monkeypatch, tmp_path, a, b)
    assert cc.main() == 0
    assert "3 days" in capsys.readouterr().out       # the incomplete day dropped
