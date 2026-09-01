"""GitHub Actions schedule reliability (closed defect loop, 2026-09-01
infra-continuity audit finding #2): a single scheduled cron is a single point
of failure — GitHub Actions cron has been observed firing 6-14h late even
against a supposed multi-hour safety margin, degrading ERCOT's receipt
coverage (2 of its last 4 scheduled runs missed their commit window; the
clock/leak guard correctly refused rather than leak, but coverage suffered).
The fix is a RETRY LADDER: multiple independent schedule entries, each still
safely before the market's hard commit deadline, so one bad delay doesn't
sink the whole day (the tick is idempotent, so extra on-time attempts are
free no-ops).

Deliberately regex-based (stdlib-only project, no PyYAML dependency) — reads
the `- cron: "..."` lines under `on: schedule:`, same pragmatic style as
test_docs_in_sync.py's markdown checks."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from talea.markets import MARKETS

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# A reference date to resolve each market's local-time deadline to a UTC
# instant (handles DST via the real zone, not a fixed offset).
REFERENCE_DATE = (2026, 9, 1)


def _crons(workflow_name: str) -> list[tuple[int, int]]:
    """[(hour, minute), ...] UTC for every `- cron: "M H * * *"` line in the
    named workflow file's `schedule:` block."""
    text = (WORKFLOWS / workflow_name).read_text()
    return [(int(h), int(m)) for m, h in
            re.findall(r'- cron:\s*"(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*"', text)]


def _deadline_utc_hour(slug: str) -> float:
    """The market's hard commit-deadline (deadline_hour, local tz) expressed
    as a UTC hour-of-day float on REFERENCE_DATE."""
    m = MARKETS[slug]
    y, mo, d = REFERENCE_DATE
    local = datetime(y, mo, d, m.deadline_hour, 0, tzinfo=m.tz)
    utc = local.astimezone(ZoneInfo("UTC"))
    return utc.hour + utc.minute / 60


def test_ercot_schedule_has_a_retry_ladder():
    """A single scheduled cron is a single point of failure against GitHub's
    documented multi-hour scheduling delays. Regression guard for the
    2026-09-01 finding: don't collapse back to one shot."""
    crons = _crons("ercot.yml")
    assert len(crons) >= 2, (
        "ercot.yml should schedule multiple independent attempts (a retry "
        "ladder), not rely on a single cron entry that a late GitHub Actions "
        "fire can sink for the whole day")


def test_ercot_schedule_entries_stay_before_the_commit_deadline():
    """Every rung of the ladder must itself fire with real margin before the
    10:00 America/Chicago hard cutoff — a ladder that schedules an entry past
    (or too close to) the deadline defeats its own purpose."""
    deadline = _deadline_utc_hour("ercot")
    min_margin_hours = 1.0
    for hour, minute in _crons("ercot.yml"):
        scheduled = hour + minute / 60
        margin = deadline - scheduled
        assert margin >= min_margin_hours, (
            f"ercot.yml cron {hour:02d}:{minute:02d} UTC leaves only "
            f"{margin:.2f}h before the {deadline:.2f} UTC commit deadline")
