"""Compat shim — the ES (apidatos.ree.es) day-ahead client moved to
`markets/es/fetch.py` in Phase 2 (2026-08-28). Re-exported so existing importers
keep working (`loop.py` still does `from .fetch import fetch_hourly`; the fetcher
tests import it here); new code imports from `esios_paper.markets.es.fetch`.

(Stage A of the ES migration: ES becomes a `markets/es/` module. The repo-root
`Data/` paths and `loop._default_market` are unchanged here — the `Data/ -> Data/es/`
move is Stage B; see docs/es-data-migration-plan.md.)
"""
from esios_paper.markets.es.fetch import API, CHUNK_DAYS, fetch_hourly  # noqa: F401

__all__ = ["API", "CHUNK_DAYS", "fetch_hourly"]
