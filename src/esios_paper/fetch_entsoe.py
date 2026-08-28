"""Compat shim — the ENTSO-E A44 client moved to `markets/_entsoe.py` (the SHARED
LIBRARY) in Phase 2 (2026-08-28). Re-exported for external importers (the fetcher
tests); MARKET code imports `markets/_entsoe` directly (importing this shim from
inside the `markets` package would be a cycle). The market-specific constants
(IT_SUD/ROME, PT/LISBON) are being relocated into their own market modules as
IT/PT migrate; this shim tracks `markets/_entsoe` during that transition.
"""
from esios_paper.markets._entsoe import (  # noqa: F401
    API, ATTRIBUTION, make_fetch, parse_a44)

# The library holds no market constants: IT owns IT_SUD/ROME (markets/it), PT owns
# PT/LISBON (markets/pt), FR owns FR/PARIS (markets/fr). This shim now re-exports
# only the shared A44 library for external/test importers.
__all__ = ["API", "ATTRIBUTION", "make_fetch", "parse_a44"]
