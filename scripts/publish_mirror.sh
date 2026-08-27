#!/usr/bin/env bash
# Publish the public mirror: render the dashboard, sync the allowlist, push.
# Called after each tick on the server. Best-effort: never fails the tick.
# The mirror checkout lives at $MIRROR_DIR (default ~/ledger-mirror) with its
# own deploy key. ALLOWLIST ONLY — ops files (CLAUDE.md, AGENTS.md, plans,
# server scripts) never leave the private repo.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
export PATH="$HOME/.local/bin:$PATH"
MIRROR="${MIRROR_DIR:-$HOME/ledger-mirror}"
[ -d "$MIRROR/.git" ] || { echo "[mirror] $MIRROR not initialized; skipping"; exit 0; }

uv run python scripts/render_dashboard.py "$MIRROR/index.html"
mkdir -p "$MIRROR/docs"
# ES data only. Silent shadow markets (de/ercot/it) accumulate PRIVATELY and
# must NOT reach the public mirror until the auditor is extended per-market
# (hard gate, docs/shadow-ledgers-*.md) — Italy additionally needs price
# redaction. Exclude every per-market subdir; ES lives in Data/ root files.
rsync -a --delete --exclude __pycache__ \
  --exclude 'de/' --exclude 'ercot/' --exclude 'it/' --exclude 'pt/' \
  Data/ "$MIRROR/Data/"
rsync -a --delete --exclude __pycache__ src/ "$MIRROR/src/"
rsync -a --delete --exclude __pycache__ tests/ "$MIRROR/tests/"
rsync -a --delete --exclude __pycache__ scripts/ "$MIRROR/scripts/"
cp VERIFY.md GOVERNANCE.md pyproject.toml uv.lock "$MIRROR/"
for d in backtest-baselines-2015-2026.md ARCHITECTURE.md \
         gate-analysis-plan.md gate-verdict-2026-08.md incidents.md \
         research-track-records-2026-08.md; do
  cp "docs/$d" "$MIRROR/docs/" 2>/dev/null || true
done
cp README-public.md "$MIRROR/README.md"

cd "$MIRROR"
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -q -m "ledger update $(date -u +%FT%TZ)"
  git push -q && echo "[mirror] published" || echo "[mirror] PUSH-FAILED (rides next publish)"
else
  echo "[mirror] up to date"
fi

# --- Germany public mirror (DE data IS redistributable: SMARD CC BY 4.0) ---
# DE is git-attested (not yet OTS-anchored); disclosed in its VERIFY.
cd "$REPO"
DEMIR="${DE_MIRROR_DIR:-$HOME/de-mirror}"
if [ -d "$DEMIR/.git" ] && [ -d Data/de ]; then
  uv run python scripts/render_dashboard.py --market de "$DEMIR/index.html"
  mkdir -p "$DEMIR/Data" "$DEMIR/docs"
  rsync -a --delete --exclude __pycache__ Data/de/ "$DEMIR/Data/"
  rsync -a --delete --exclude __pycache__ src/ "$DEMIR/src/"
  rsync -a --delete --exclude __pycache__ tests/ "$DEMIR/tests/"
  cp GOVERNANCE.md pyproject.toml uv.lock "$DEMIR/"
  cp README-de.md "$DEMIR/README.md"
  cp VERIFY-de.md "$DEMIR/VERIFY.md"
  cd "$DEMIR"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -q -m "DE ledger update $(date -u +%FT%TZ)"
    git push -q && echo "[de-mirror] published" || echo "[de-mirror] PUSH-FAILED"
  else
    echo "[de-mirror] up to date"
  fi
fi
