#!/usr/bin/env bash
# Weekly maintenance (systemd esios-ots-upgrade.timer, Sun 12:00 Madrid):
#   1) refresh the token-route dataset — the independent source
#   2) cross-validate the two routes (a failure lands in git, loudly)
#   3) upgrade pending OpenTimestamps proofs to Bitcoin-anchored ones
#   4) commit whatever changed
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
git pull --ff-only || true

PYTHONPATH=tools/esios-fetcher uv run --no-dev python -m esios_fetcher \
  || echo "[weekly] token-route refresh FAILED"

if ! uv run --no-dev python scripts/crosscheck_routes.py; then
  echo "$(date -u +%FT%TZ) cross-check failed or inconclusive" \
    >> Data/CROSSCHECK-ALERTS.log
fi

if ! uv run --no-dev python scripts/audit_ots_manifests.py; then
  echo "$(date -u +%FT%TZ) unstamped ots manifest(s) found" \
    >> Data/OTS-GAPS.log
fi

# Every market's OTS proofs (ES now at Data/es/ots; all markets covered uniformly,
# fixing the old es+de-only list). Data/<slug>/ots/*.txt.ots.
for f in Data/*/ots/*.txt.ots; do
  [ -e "$f" ] || continue
  uvx --from opentimestamps-client==0.7.2 ots upgrade "$f" || true   # pinned (see __main__.OTS_CLIENT)
done
rm -f Data/*/ots/*.bak

if [ -n "$(git status --porcelain Data)" ]; then
  git add Data
  git commit -m "data: weekly maintenance (route refresh + cross-check + ots upgrade)"
  git push
fi
