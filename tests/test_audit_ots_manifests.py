"""Regression for the 2026-08-24 audit finding: Data/ots/2026-08-10-2.txt
(and 12 sibling dates) hold the real, final settlement state but were never
submitted to OpenTimestamps, so 13 dates' Bitcoin anchor covers only an
earlier, partial intra-day state. scripts/audit_ots_manifests.py must flag
any written-but-unstamped manifest so this class never goes unnoticed again.
"""
import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "audit_ots_manifests",
    Path(__file__).resolve().parents[1] / "scripts" / "audit_ots_manifests.py",
)
audit_ots_manifests = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_ots_manifests)


def test_flags_manifest_written_without_a_matching_proof(tmp_path):
    (tmp_path / "2026-08-10.txt").write_text("stamped state\n")
    (tmp_path / "2026-08-10.txt.ots").write_bytes(b"proof")
    (tmp_path / "2026-08-10-2.txt").write_text("displaced, never stamped\n")

    gaps = audit_ots_manifests.find_unstamped(tmp_path, today="2026-08-24")

    assert gaps == ["2026-08-10-2.txt"]


def test_todays_manifest_is_exempt_even_if_not_yet_stamped(tmp_path):
    (tmp_path / "2026-08-24.txt").write_text("just written\n")

    gaps = audit_ots_manifests.find_unstamped(tmp_path, today="2026-08-24")

    assert gaps == []


def test_fully_stamped_directory_has_no_gaps(tmp_path):
    (tmp_path / "2026-08-09.txt").write_text("state\n")
    (tmp_path / "2026-08-09.txt.ots").write_bytes(b"proof")

    gaps = audit_ots_manifests.find_unstamped(tmp_path, today="2026-08-24")

    assert gaps == []
