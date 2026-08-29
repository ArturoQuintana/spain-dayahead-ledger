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

from talea.loop import STRATEGIES
from talea.markets import MARKETS

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


def test_verify_discloses_migrated_market_evidence_boundaries():
    """Incident 2026-08-29 (independent auditor): consolidating markets into the
    one `talea` repo makes a migrated market's git-history in THIS repo begin with
    a bulk sync, so the timing 'weak check' (committed_at vs the commit that
    introduced a receipt) cannot corroborate its pre-migration dates from this repo
    alone. VERIFY.md MUST disclose that boundary for every migrated-in public
    market — as it already does for ES's pre-2026-08-10 mirror bulk import — or the
    'git-attested' label overclaims. Guards the ES and DE disclosures against being
    dropped in a future VERIFY rewrite.

    A second, same-day audit pass found the identical gap for ERCOT: its receipts
    also entered this repo in the single fd4bdd49 consolidation commit, but
    VERIFY.md's per-market tier section disclosed the boundary only for DE, not
    ERCOT (which it instead described as plain 'git-attested from their first
    tick' — the overclaim). Guard that disclosure too."""
    v = (ROOT / "VERIFY.md").read_text().lower()
    assert "2026-08-10" in v and "bulk" in v, \
        "VERIFY.md must disclose ES's pre-2026-08-10 bulk-import evidence boundary"
    assert "evidence boundary" in v, \
        "VERIFY.md must name the evidence-boundary concept for migrated markets"
    assert "germany-dayahead-ledger" in v or "consolidation" in v, \
        ("VERIFY.md must disclose DE's evidence boundary — its talea git-history "
         "begins with the 2026-08-29 consolidation sync, per-tick history lives "
         "in the private repo / frozen germany-dayahead-ledger mirror")
    assert "- **ercot**" in v, "VERIFY.md must give ERCOT its own tier bullet"
    ercot_bullet = v.split("- **ercot**", 1)[1].split("\n- **", 1)[0]
    assert "fd4bdd49" in ercot_bullet and "evidence boundary" in ercot_bullet, \
        ("VERIFY.md's ERCOT bullet must disclose the same consolidation-commit "
         "evidence boundary as DE's — not just describe ERCOT as plain "
         "'git-attested from their first tick'")


def test_every_public_market_has_a_colocated_data_licence():
    """Licensing travels with the data: each PUBLISHED market carries its own
    Data/<slug>/LICENSE.md (source + licence + attribution) and is indexed in
    DATA-SOURCES.md. A public market missing its licence file could redistribute
    third-party price data with no attribution — a licence breach. (Private
    markets are never published, so they need no public licence file.)"""
    from talea.markets import public_markets
    index = (ROOT / "DATA-SOURCES.md").read_text()
    for m in public_markets():
        lic = ROOT / "Data" / m.slug / "LICENSE.md"
        assert lic.exists(), \
            f"public market {m.slug!r} has no Data/{m.slug}/LICENSE.md"
        assert f"Data/{m.slug}/" in index, \
            f"{m.slug!r} is public but missing from the DATA-SOURCES.md index"


def test_mirror_is_deny_by_default_allowlist():
    """Incident 2026-08-28: FR (private, derived-only) leaked to the PUBLIC mirror
    through a DENY-LIST gap — fr/ was never added to the excludes. The Talea mirror
    (one project, all public markets under Data/<slug>/) must be a POSITIVE
    ALLOWLIST (deny-by-default): a terminal --exclude='*' so anything not named
    cannot leak, per-market includes REGISTRY-DERIVED (a loop over
    `markets --public`) so no PRIVATE market is ever named, and a fail-safe that
    skips publishing when the lookup is empty (so a bad lookup can never
    --delete-excluded the whole mirror). Leaking a private market now requires
    flagging it public in the registry, not forgetting an exclude."""
    from talea.markets import public_markets
    txt = (ROOT / "scripts" / "publish_mirror.sh").read_text()
    assert "--exclude='*'" in txt, \
        "mirror publish must end in a deny-all --exclude='*' (allowlist posture)"
    assert "for s in $SLUGS" in txt and '--include="/$s/***"' in txt, \
        ("public-market includes must be REGISTRY-DERIVED (loop over "
         "`markets --public`), not hardcoded per market")
    assert 'if [ -z "$SLUGS" ]' in txt, \
        "mirror publish must fail-safe (skip) when the public-market lookup is empty"
    public = {m.slug for m in public_markets()}
    for slug in MARKETS:
        if slug in public:
            continue
        assert f"--include='/{slug}/" not in txt and f'--include="/{slug}/' not in txt, \
            (f"{slug!r} is PRIVATE but explicitly --include'd in the mirror "
             f"allowlist — a private market must never be published.")
