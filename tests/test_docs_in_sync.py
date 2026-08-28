"""Documentation-drift detectors (closed defect loop: doc staleness is a
failure class, so it gets a regression test). These FAIL the build when a
market or strategy is added in code but not named in the docs — which is
exactly how ARCHITECTURE.md fell behind the multi-market build.

Deliberately cheap: they check that each code-registered name APPEARS in the
canonical doc, not that prose is worded a particular way. Live numbers are NOT
checked here — those belong in the ledger/status/dashboard, never frozen in a
doc."""
import re
from pathlib import Path

from esios_paper.loop import STRATEGIES
from esios_paper.markets import MARKETS

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
CLAUDE = (ROOT / "CLAUDE.md").read_text()


def test_every_market_is_documented():
    """Each registered market slug must appear (as an upper-case token) in the
    ARCHITECTURE markets inventory."""
    missing = [slug for slug in MARKETS
               if not re.search(rf"\b{slug.upper()}\b", ARCHITECTURE)]
    assert not missing, (
        f"markets in code but not in docs/ARCHITECTURE.md: {missing} — "
        f"update the Markets table when you register a market")


def test_every_strategy_is_documented():
    """Each registered strategy's short name must appear in BOTH the
    ARCHITECTURE panel and CLAUDE.md's registered panel."""
    names = [s["strategy"].replace("battery-2h2h-", "") for s in STRATEGIES]
    missing_arch = [n for n in names if n not in ARCHITECTURE]
    missing_claude = [n for n in names if n not in CLAUDE]
    assert not missing_arch, (
        f"strategies in code but not in docs/ARCHITECTURE.md panel: {missing_arch}")
    assert not missing_claude, (
        f"strategies in code but not in CLAUDE.md registered panel: {missing_claude}")


def _architecture_market_rows():
    """The rows of the ARCHITECTURE.md Markets table, keyed by slug."""
    body = ARCHITECTURE.split("## Markets", 1)[1].split("\n## ", 1)[0]
    slugs = {s.upper() for s in MARKETS}
    return {mm.group(1).lower(): line for line in body.splitlines()
            if (mm := re.match(r"\s+([A-Z]{2,6})\b", line)) and mm.group(1) in slugs}


def test_architecture_table_lists_exactly_the_registered_markets():
    assert set(_architecture_market_rows()) == set(MARKETS)


def test_architecture_table_flags_match_the_registry():
    rows = _architecture_market_rows()
    for slug, m in MARKETS.items():
        line = rows[slug]
        assert ("private" in line) != m.public, f"{slug} public flag drift: {line}"
        assert ("Actions" in line) == (m.driver == "actions"), \
            f"{slug} driver flag drift: {line}"


def test_es_mirror_excludes_are_registry_derived():
    """Incident 2026-08-28: FR (private, derived-only) leaked to the PUBLIC ES
    mirror because publish_mirror.sh's exclude list was HARDCODED (de/ercot/it/pt)
    and never updated when FR was added. Detector: the ES-data rsync must derive
    its excludes from the registry (so a new market can never leak), and must NOT
    hardcode a per-market --exclude for any registered non-es market."""
    txt = (ROOT / "scripts" / "publish_mirror.sh").read_text()
    assert "esios_paper markets" in txt, \
        "ES mirror excludes must be DERIVED from the registry, not hardcoded"
    for slug in MARKETS:
        if slug == "es":
            continue
        assert f"--exclude '{slug}/'" not in txt and f"--exclude={slug}/" not in txt, \
            (f"publish_mirror.sh hardcodes an --exclude for {slug!r}; that list "
             f"drifts when a market is added (see the FR leak). Derive it from the "
             f"markets CLI instead.")
