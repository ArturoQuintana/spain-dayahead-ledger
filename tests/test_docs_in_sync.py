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


def test_es_mirror_is_deny_by_default_allowlist():
    """Incident 2026-08-28: FR (private, derived-only) leaked to the PUBLIC ES
    mirror through a DENY-LIST gap — fr/ was never added to the excludes. The
    ES-data publish must instead be a POSITIVE ALLOWLIST (deny-by-default): a
    terminal --exclude='*' so anything not explicitly named cannot leak, and NO
    non-es market may be explicitly included. A new market or a stray root file is
    then excluded because it is not on the list — leaking requires consciously
    adding it, not forgetting to exclude it."""
    txt = (ROOT / "scripts" / "publish_mirror.sh").read_text()
    assert "--exclude='*'" in txt, \
        "ES-mirror publish must end in a deny-all --exclude='*' (allowlist posture)"
    for slug in MARKETS:
        if slug == "es":
            continue
        assert f"--include='/{slug}/" not in txt and f"--include=/{slug}/" not in txt, \
            (f"{slug!r} is explicitly --include'd in a mirror allowlist; only es "
             f"belongs on the ES mirror (see the FR leak).")
