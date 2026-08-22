#!/usr/bin/env bash
# The server tick: pull (the Mac still pushes code/docs), then run the daily
# pass. Invoked by systemd (esios-tick.timer, 11:00 + 17:00 Europe/Madrid,
# Persistent=true). The tick itself owns all safety (leak guard, retries).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
git pull --ff-only || echo "[esios-paper] pre-tick pull failed (continuing on local state)"
# Silent shadow markets FIRST (best-effort, never affect the ES tick): their
# Data/<slug>/ changes ride the ES tick's git_backup. No heartbeat/email/OTS
# for these — they accumulate privately (not mirrored) until the auditor is
# extended per-market. The 11:00 Madrid slot = 11:00 Berlin (<12:00 DE gate)
# = 04:00 CT (<10:00 ERCOT deadline): pre-publication for both.
for m in de ercot; do
  uv run python -m esios_paper tick --market "$m" \
    || echo "[esios-paper] $m tick failed (non-fatal, silent market)"
done
uv run python -m esios_paper tick          # ES: commits Data/ (all markets)
rc=$?
scripts/publish_mirror.sh || echo "[esios-paper] mirror publish failed (non-fatal)"
exit $rc
