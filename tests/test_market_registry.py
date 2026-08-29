"""Drift-proof tests for the market registry (Phase 0 of the market-plugin
refactor). Before Phase 0 there were five hand-synced market lists and the
dashboard renderer had silently dropped PT and ERCOT. These assert every
registered market is reachable from every operational surface, so that class of
drift fails the build."""
import importlib.util
from pathlib import Path

from talea import markets as reg

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_exactly_one_primary_and_the_rest_are_shadows():
    assert sum(m.primary for m in reg.MARKETS.values()) == 1
    partition = {m.slug for m in reg.shadows()} | {
        m.slug for m in reg.MARKETS.values() if m.primary}
    assert partition == set(reg.MARKETS)


def test_query_helpers_match_the_flags():
    assert {m.slug for m in reg.public_markets()} == {"es", "de", "gb", "ercot"}
    assert {m.slug for m in reg.by_driver("actions")} == {"ercot", "jp"}
    assert {m.slug for m in reg.by_driver("server")} == {"de", "it", "pt", "fr", "gb"}
    # by_driver never returns the primary (the ES pass runs it directly)
    assert all(not m.primary for m in reg.by_driver("server"))


def test_render_dashboard_presentation_covers_every_market():
    # THE regression that motivated Phase 0: the renderer's market set is now
    # derived from the registry, so no market can be silently missing again.
    rd = _load_script("render_dashboard")
    assert set(rd.MARKETS) == set(reg.MARKETS)


def test_every_market_has_presentation_and_a_tz_label():
    for slug, m in reg.MARKETS.items():
        assert m.presentation.title, f"{slug} has no dashboard title"
        assert m.presentation.tz_label, f"{slug} has no tz label"
        assert m.presentation.tab_name, f"{slug} has no tab name"
