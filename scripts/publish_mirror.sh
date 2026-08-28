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

uv run --no-dev python scripts/render_dashboard.py "$MIRROR/index.html"
mkdir -p "$MIRROR/docs"
# The ES mirror is ES-ONLY (ES now lives in Data/es/, Stage B). Exclude every
# OTHER market subdir, DERIVED FROM THE REGISTRY — not a hardcoded list, so a newly
# added market can NEVER leak into the public mirror. (Incident 2026-08-28: FR
# leaked because the old hardcoded list — de/ercot/it/pt — was not updated when FR
# was added.) --delete-excluded purges any such dir already in the mirror; also
# drop transient .tick.lock files. Only es/ + shared artifacts (esios_prices.json,
# calibration/, README-MOVED.md) reach the public ES mirror.
ES_EXCLUDES="--exclude=.tick.lock"
for s in $(uv run --no-dev python -m esios_paper markets); do
  [ "$s" = "es" ] || ES_EXCLUDES="$ES_EXCLUDES --exclude=$s/"
done
rsync -a --delete --delete-excluded --exclude __pycache__ $ES_EXCLUDES \
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
# The mirror runs its OWN verify workflow so the README badge is a real,
# anonymously-verifiable check on GitHub's infra (deploy keys may push workflow
# files; PATs without `workflow` scope may not — we push via the mirror's key).
mkdir -p "$MIRROR/.github/workflows"
cp mirror/verify.yml "$MIRROR/.github/workflows/verify.yml"

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
  uv run --no-dev python scripts/render_dashboard.py --market de "$DEMIR/index.html"
  mkdir -p "$DEMIR/Data" "$DEMIR/docs"
  rsync -a --delete --exclude __pycache__ Data/de/ "$DEMIR/Data/"
  rsync -a --delete --exclude __pycache__ src/ "$DEMIR/src/"
  rsync -a --delete --exclude __pycache__ tests/ "$DEMIR/tests/"
  rsync -a --delete --exclude __pycache__ scripts/ "$DEMIR/scripts/"
  cp GOVERNANCE.md pyproject.toml uv.lock "$DEMIR/"
  cp README-de.md "$DEMIR/README.md"
  cp VERIFY-de.md "$DEMIR/VERIFY.md"
  # Same real, anonymously-verifiable green badge as the ES mirror: the DE repo
  # re-derives its own ledger with verify_ledger.py on GitHub's infra.
  mkdir -p "$DEMIR/.github/workflows"
  cp mirror/verify.yml "$DEMIR/.github/workflows/verify.yml"
  cd "$DEMIR"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -q -m "DE ledger update $(date -u +%FT%TZ)"
    git push -q && echo "[de-mirror] published" || echo "[de-mirror] PUSH-FAILED"
  else
    echo "[de-mirror] up to date"
  fi
fi
