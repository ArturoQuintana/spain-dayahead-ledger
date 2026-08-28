#!/usr/bin/env bash
# The server tick: pull (the Mac still pushes code/docs), then run the daily
# pass. Invoked by systemd (esios-tick.timer, 11:00 + 17:00 Europe/Madrid,
# Persistent=true). The tick itself owns all safety (leak guard, retries).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
git pull --ff-only || echo "[esios-paper] pre-tick pull failed (continuing on local state)"
# Silent shadow markets FIRST (best-effort, never affect the ES tick): their
# Data/<slug>/ changes ride the ES tick's git_backup. They DO OTS-anchor (each
# gets its own Data/<slug>/ots Bitcoin proof — see cmd_tick + the test
# test_cmd_tick_silent_market_skips_heartbeat_email_git_ots); they skip only the
# heartbeat, email, and their OWN git push. They accumulate privately (not
# mirrored). The 11:00 Madrid slot = 11:00 Berlin/Paris (<12:00 DE/FR gate)
# = 04:00 CT (<10:00 ERCOT deadline): pre-publication for all.
# The server-driven shadow set comes from the REGISTRY (markets with
# driver="server", non-primary) — not a hardcoded list (Phase 0). ERCOT is
# driver="actions" (ercot.com 403s this Helsinki server — geo-block, incident
# 2026-08-23), so it's excluded here and runs on GitHub Actions instead; adding
# or moving a market never touches this script.
for m in $(uv run --no-dev python -m esios_paper markets --driver server); do
  uv run --no-dev python -m esios_paper tick --market "$m" \
    || echo "[esios-paper] $m tick failed (non-fatal, silent market)"
done
uv run --no-dev python -m esios_paper tick          # ES: commits Data/ (all markets)
rc=$?
# Pillar B — liveness monitor (2026-08-28): page if any REGISTERED market has
# silently stopped committing (>48h since its last receipt) — the one harm
# verify_ledger cannot see (a dark market writes nothing to verify). Runs after
# all ticks so it sees the freshest state; best-effort, never affects the tick exit.
if ! LIVENESS=$(uv run --no-dev python scripts/check_liveness.py --quiet 2>&1); then
  echo "[esios-paper] LIVENESS ALERT:"; echo "$LIVENESS"
  curl -s -m 20 -H 'Title: esios LIVENESS' -H 'Priority: high' -H 'Tags: rotating_light' \
    -d "a market has gone dark: $LIVENESS" https://ntfy.sh/esios-2b32d5ab08012283 || true
fi
scripts/publish_mirror.sh || echo "[esios-paper] mirror publish failed (non-fatal)"
exit $rc
