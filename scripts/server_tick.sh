#!/usr/bin/env bash
# The server tick: pull (the Mac still pushes code/docs), then run the daily
# pass. Invoked by systemd (esios-tick.timer, 11:00 + 17:00 Europe/Madrid,
# Persistent=true). The tick itself owns all safety (leak guard, retries).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
git pull --ff-only || echo "[esios-paper] pre-tick pull failed (continuing on local state)"
uv run python -m esios_paper tick
rc=$?
scripts/publish_mirror.sh || echo "[esios-paper] mirror publish failed (non-fatal)"
exit $rc
