"""Tests for Pillar B — the market liveness monitor.

The behaviour that matters: a market that has silently stopped committing must be
flagged STALE and must fail the exit (so a caller can page), while an honest single
missed day and an onboarding market must NOT false-alarm.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import check_liveness as cl  # noqa: E402

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _receipts(tmp_path: Path, slug: str, ages_h: list[float] | None) -> SimpleNamespace:
    """A fake market whose receipts were committed `ages_h` hours before NOW.
    ages_h=None => no receipts file at all (the NEVER case)."""
    p = tmp_path / f"{slug}.jsonl"
    if ages_h is not None:
        lines = [json.dumps({"target": "2026-08-28",
                             "committed_at": (NOW - timedelta(hours=h)).isoformat()})
                 for h in ages_h]
        p.write_text("\n".join(lines) + "\n")
    return SimpleNamespace(slug=slug, receipts_path=p)


def test_healthy_market_recent_commit(tmp_path):
    m = _receipts(tmp_path, "de", [10.0])
    r = cl.market_liveness(m.slug, m.receipts_path, NOW)
    assert r["state"] == "HEALTHY" and r["age_h"] == 10.0


def test_stale_market_two_days_dark(tmp_path):
    m = _receipts(tmp_path, "it", [60.0])
    r = cl.market_liveness(m.slug, m.receipts_path, NOW)
    assert r["state"] == "STALE"


def test_never_committed_is_not_stale(tmp_path):
    m = _receipts(tmp_path, "gb", None)   # registered, no receipts file
    r = cl.market_liveness(m.slug, m.receipts_path, NOW)
    assert r["state"] == "NEVER" and r["age_h"] is None


def test_threshold_is_strict_at_48h(tmp_path):
    assert cl.market_liveness("a", _receipts(tmp_path, "a", [48.0]).receipts_path, NOW)["state"] == "HEALTHY"
    assert cl.market_liveness("b", _receipts(tmp_path, "b", [48.01]).receipts_path, NOW)["state"] == "STALE"


def test_newest_commit_takes_the_max_and_skips_junk(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({"committed_at": (NOW - timedelta(hours=90)).isoformat()}) + "\n"
                 + "\n"                                                   # blank line
                 + json.dumps({"target": "x"}) + "\n"                    # no committed_at
                 + json.dumps({"committed_at": (NOW - timedelta(hours=5)).isoformat()}) + "\n")
    assert cl.newest_commit(p) == NOW - timedelta(hours=5)


def test_empty_receipts_file_is_never(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    assert cl.newest_commit(p) is None


def test_main_exits_nonzero_on_stale_and_names_it(tmp_path, capsys):
    markets = [_receipts(tmp_path, "es", [12.0]),
               _receipts(tmp_path, "it", [72.0]),      # stale
               _receipts(tmp_path, "gb", None)]        # never
    rc = cl.main([], market_list=markets, now=NOW)
    out = capsys.readouterr().out
    assert rc == 1
    assert "STALE" in out and "it" in out
    assert "NEVER" in out and "gb" in out


def test_main_all_live_exits_zero(tmp_path, capsys):
    markets = [_receipts(tmp_path, "es", [12.0]), _receipts(tmp_path, "de", [20.0])]
    rc = cl.main([], market_list=markets, now=NOW)
    assert rc == 0
    assert "all markets live" in capsys.readouterr().out


def test_main_never_only_is_healthy_exit(tmp_path, capsys):
    markets = [_receipts(tmp_path, "es", [12.0]), _receipts(tmp_path, "gb", None)]
    rc = cl.main([], market_list=markets, now=NOW)
    assert rc == 0
    assert "NEVER (info)" in capsys.readouterr().out


def test_main_quiet_suppresses_healthy_lines(tmp_path, capsys):
    markets = [_receipts(tmp_path, "es", [12.0]), _receipts(tmp_path, "it", [72.0])]
    cl.main(["--quiet"], market_list=markets, now=NOW)
    out = capsys.readouterr().out
    assert "es" not in out.split("->")[0]   # healthy line suppressed
    assert "it" in out                       # stale still shown


def test_main_custom_stale_hours(tmp_path, capsys):
    markets = [_receipts(tmp_path, "es", [30.0])]
    assert cl.main(["--stale-hours", "24"], market_list=markets, now=NOW) == 1  # 30h > 24h
    assert cl.main(["--stale-hours", "48"], market_list=markets, now=NOW) == 0  # 30h < 48h


def test_assess_maps_all_markets(tmp_path):
    markets = [_receipts(tmp_path, "es", [1.0]), _receipts(tmp_path, "de", [99.0])]
    rows = cl.assess(markets, NOW)
    assert {r["slug"]: r["state"] for r in rows} == {"es": "HEALTHY", "de": "STALE"}
