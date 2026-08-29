"""The registry of markets the loop runs — the SINGLE SOURCE OF TRUTH.

Each market carries its own timezone, commit deadline (local clock, before its
auction publishes), currency, Data/<slug>/ tree, fetch client, and FLAGS
(primary/public/driver/redistributable + presentation). Operational surfaces —
the email digest, server_tick.sh, render_dashboard.py, publish_mirror.sh, the
ARCHITECTURE Markets table — query this registry and branch on the flags rather
than hardcoding slug subsets (Phase 0 of the market-plugin refactor, 2026-08-27;
before it there were five drifting hand-synced lists).

Phase 1 (2026-08-28): `markets.py` became the `markets/` package. The public API
(`MARKETS`, `shadows`, `public_markets`, `by_driver`, and the contract types) is
unchanged, so every `from esios_paper.markets import …` keeps working. The
contract now lives in `base.py`; per-market plugins (`markets/<slug>/`) land here
in later phases.
"""
from __future__ import annotations

from .base import Fetcher, Market, Presentation  # the contract surface

__all__ = ["MARKETS", "shadows", "public_markets", "by_driver",
           "Market", "Presentation", "Fetcher"]

# Spain: the primary. Migrated to a vertical markets/es/ module in Phase 2
# (2026-08-28) — the last incumbent, imported like the others. STAGE A keeps ES on
# the repo-root Data/ paths; the Data/ -> Data/es/ move is Stage B
# (docs/es-data-migration-plan.md).
from .es import MARKET as ES  # noqa: E402

# Germany (DE-LU): SMARD.de, CC BY 4.0. Public. Gate 12:00 CET. Migrated to a
# vertical markets/de/ module in Phase 2 (2026-08-28) — imported, not inline.
from .de import MARKET as DE  # noqa: E402

# Italy (IT-SUD): independent ENTSO-E market. Migrated to a vertical markets/it/
# module in Phase 2 (2026-08-28) — owns its EIC/tz, binds _entsoe inline.
from .it import MARKET as IT  # noqa: E402

# Portugal (PT): independent ENTSO-E market (real PT-zone, not an ES relabel).
# Migrated to a vertical markets/pt/ module in Phase 2 (2026-08-28).
from .pt import MARKET as PT  # noqa: E402

# ERCOT (Texas): DAM SPP, HB_NORTH, USD, driver=actions. Migrated to a vertical
# markets/ercot/ module in Phase 2 (2026-08-28) — imported, not inline.
from .ercot import MARKET as ERCOT  # noqa: E402

# France (FR): the first market as a VERTICAL markets/<slug>/ module (Phase 1.5,
# 2026-08-28) — imported, not defined inline. ENTSO-E derived-only/private like
# IT/PT; flagship of the SDAC FR/BE/NL cluster. The incumbents above migrate into
# this same shape in Phase 2.
from .fr import MARKET as FR  # noqa: E402

# Great Britain: Elexon BMRS (redistributable/open), SILENT-FIRST (public=False).
# The shortlist's #1; first market on the finished plugin architecture (2026-08-28).
from .gb import MARKET as GB  # noqa: E402

# Japan: JEPX spot (redistributable/attribution), SILENT-FIRST, driver="actions"
# (publishes ~10:10 JST = European night — GitHub Actions ticks it, like ERCOT).
from .jp import MARKET as JP  # noqa: E402

# Registry by slug. Order: primary first, then shadows in digest order (ENTSO-E
# EU-derived it/pt/fr grouped; GB; JP; ERCOT — the two Actions/US-JP markets last).
MARKETS = {m.slug: m for m in (ES, DE, IT, PT, FR, GB, JP, ERCOT)}


# --- registry queries: the ONLY way operational surfaces should enumerate ---

def shadows() -> list[Market]:
    """Non-primary markets, in registry order (the email digest's set)."""
    return [m for m in MARKETS.values() if not m.primary]


def public_markets() -> list[Market]:
    """Markets with a public mirror + dashboard (publish_mirror's set)."""
    return [m for m in MARKETS.values() if m.public]


def by_driver(driver: str) -> list[Market]:
    """Markets driven by `driver` ('server' | 'actions'); excludes the primary,
    which the ES pass runs directly (server_tick / Actions consumers)."""
    return [m for m in MARKETS.values() if m.driver == driver and not m.primary]
