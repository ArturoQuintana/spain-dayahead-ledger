"""Detect OTS manifest slots that were written but never stamped.

Class this closes: the 2026-08-21 fix made stamped manifests immutable (a
changed audit trail gets a NEW suffixed slot instead of overwriting the
stamped one) but that only guarantees the *old* slot stays intact — it does
not guarantee every new slot actually gets stamped. A 2026-08-24 audit found
13 such gaps predating the fix (Data/ots/<date>-2.txt files holding the real,
final settlement state for 2026-08-09 through 2026-08-21, written during the
08-21 restoration but never submitted to OpenTimestamps) plus the structural
consequence: those 13 dates' Bitcoin anchor covers only an earlier, partial
intra-day state, not the final one. This script re-finds that condition so
it can never again go unnoticed for a full audit cycle.

A manifest dated TODAY is exempt: `ots stamp` can legitimately not have run
yet, or its own weekly upgrade (Sun 12:00) may still be pending — that is
normal, not a gap.

Run: uv run python scripts/audit_ots_manifests.py
Exit 0 = every non-today manifest is stamped; exit 1 = gaps found (printed).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

OTS_DIR = Path(__file__).resolve().parents[1] / "Data" / "es" / "ots"  # ES at Data/es/ (Stage B)


def find_unstamped(ots_dir: Path, today: str) -> list[str]:
    """Return sorted names of *.txt manifests with no sibling *.txt.ots,
    excluding today's (proof may not have been submitted yet)."""
    gaps = []
    for manifest in sorted(ots_dir.glob("*.txt")):
        if manifest.name.startswith(today):
            continue
        if not manifest.with_suffix(".txt.ots").exists():
            gaps.append(manifest.name)
    return gaps


def main() -> int:
    if not OTS_DIR.exists():
        print("[ots-audit] Data/es/ots absent; nothing to check")
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    gaps = find_unstamped(OTS_DIR, today)
    if not gaps:
        print("[ots-audit] every non-today manifest is stamped")
        return 0
    print(f"[ots-audit] {len(gaps)} manifest(s) written but never stamped "
          "(no Bitcoin anchor for that file state):")
    for name in gaps:
        print(f"  Data/es/ots/{name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
