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
