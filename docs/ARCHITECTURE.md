# Architecture

What this application does: every day, BEFORE a day-ahead auction publishes
tomorrow's electricity prices, it commits immutable "receipts" recording how a
panel of pre-registered strategies would trade a virtual 1 MW / 2 MWh battery;
after publication it settles those receipts against the real prices, appends
money-denominated results to an append-only ledger, anchors everything in
Bitcoin via OpenTimestamps, and republishes a public, auditable dashboard. It
is a measurement instrument: the product is a track record that cannot be
faked, revised, or cherry-picked. Spain is the primary market; the same loop
now runs five markets (see "Markets" below). Governance (who may change what,
and how claims are verified) is in CLAUDE.md; outsider verification in
VERIFY.md.

## Markets (updated 2026-08-27)

The loop is market-agnostic (a frozen `Market` dataclass parameterizes zone,
timezone, commit deadline, currency, Data/<slug>/ tree, and fetch client — the
strategy panel, P&L math, and guards are shared). Five markets run today:

    market  zone      source / license               cur  deadline  writer        public tier
    ES      Spain     apidatos.ree.es · public        EUR  13:00     server        Pages + Bitcoin-OTS
    DE      DE-LU     SMARD.de · CC BY 4.0            EUR  12:00     server        Pages + OTS
    IT      IT-SUD    ENTSO-E A44 · token, derived    EUR  12:00     server        private (license)
    PT      PT        ENTSO-E A44 · token, derived    EUR  12:00     server        private (license)
    ERCOT   HB_NORTH  ERCOT MIS NP4-190 · public/redist USD 10:00    GitHub Actions private + OTS

Two writers, not one: the server writes ES/DE/IT/PT; ERCOT is driven from
GitHub Actions US runners (ERCOT DAM geo-blocks EU IPs). Both push directly to
`main`; the `main-protection` ruleset blocks force-push and branch deletion so
the append-only trail cannot be rewritten. IT/PT are private because ENTSO-E
day-ahead is not freely redistributable (derived-metrics-only if ever
published); ERCOT is redistributable and could go public later. Historical
cross-market capture is in docs/backtest-markets-2026-08.md.

## Components

    ┌──────────────── Hetzner VPS (primary writer; ERCOT via GitHub Actions) ────────┐
    │ systemd timers                                                                │
    │  esios-tick.timer      11:00 / 12:30 / 17:00 Europe/Madrid → server_tick.sh   │
    │  esios-ots-upgrade     Sun 12:00 Madrid → weekly_maintenance.sh               │
    │                                                                               │
    │ server_tick.sh: git pull → python -m esios_paper tick → publish_mirror.sh     │
    └──────────────┬──────────────────────────────────────────────┬─────────────────┘
                   │ git push (audit trail)                       │ git push (allowlist)
                   ▼                                              ▼
        GitHub private repo                          GitHub public mirror ── Pages
        (code + Data/)                               (Data/, src/, VERIFY, dashboard)
                   ▲                                              │
                   │ analysis clone, sessions                     ▼ raw reads (no auth)
              Mac (cockpit)                          Cloud routines (claude.ai):
                                                      - daily digest 16:35 UTC
                                                      - Monday independent auditor

    External: apidatos.ree.es (price route A) · api.esios.ree.es (route B,
    weekly cross-check) · OTS calendar servers → Bitcoin · healthchecks.io
    (dead-man) · Gmail SMTP 587 (inbox digest)

## Package layout

    src/esios_paper/
      fetch.py     route-A client: quarter-hour API → hourly means,
                   {"YYYY-MM-DDTHH": price}, Europe/Madrid frame. Owns nothing.
      loop.py      THE CORE. Pure functions + the tick orchestrator. Owns the
                   strategies, leak guard, settlement math, telemetry.
      __main__.py  effectful shell: CLI, git backup, OTS stamping, heartbeat,
                   email digest. Injection seams (_smtp, _urlopen, _run) for tests.
    tools/esios-fetcher/   route-B client (token, PriceDay contract, own tests)
    scripts/               server_tick, weekly_maintenance, publish_mirror,
                           render_dashboard, backtest, compare, crosscheck
    tests/                 78 tests, failure-mode-first
    Data/                  the product (see Data flow)

## Call flow of one tick (loop.tick, via __main__.cmd_tick)

    1. today = market_today()            # Europe/Madrid date, machine-TZ-proof
    2. FETCH  fetch_hourly(last_known → tomorrow)
              retries +5m/+15m; validate_prices rails (-500..4000, finite);
              a failing/insane fetch NEVER touches the dataset (stale is safe)
    3. SETTLE for every receipt whose target day is now fully published and
              not yet in the ledger (keyed target+strategy+version):
                pnl_eur(buy, sell, actual)      # 0.85 RT on sell leg, 0.5 fees
                oracle = pnl_eur(pick_hours(actual))   # perfect hindsight
                capture = pnl/oracle · tau = kendall_tau(basis_profile, actual)
                + regime telemetry (neg_hours, tb2_spread)  → append ledger
    4. COMMIT (tomorrow's receipts) — THE LEAK GUARD:
                if any price for tomorrow exists in OUR dataset → refuse all
                else for each STRATEGIES entry: basis_fn(prices, today) →
                  (basis|None, why); pick_hours(basis) → receipt appended
                  (idempotent per target+strategy; includes basis_profile)
    5. __main__ shell, in order (each best-effort, never fatal):
                OTS stamp (manifest of receipts+ledger hashes) → git commit+
                push Data/ → heartbeat (ping iff primary receipt stands;
                /fail otherwise) → email digest (only on settle or trouble)
    6. server_tick.sh: render_dashboard → publish_mirror (allowlist → Pages)

## Data flow and formats

    apidatos ──fetch──▶ Data/prices.json          [{"ts","price"}] hourly,
                                                  dataset of record; leak guard
                                                  is defined against THIS file
    strategies ─commit─▶ Data/receipts.jsonl      append-only; target, hours,
                                                  basis_day, basis_profile,
                                                  params, committed_at (UTC)
    publication ─settle─▶ Data/ledger.jsonl       append-only; pnl_eur, oracle,
                                                  capture, tau, neg_hours,
                                                  tb2_spread, settled_at
    both ──sha256──▶ Data/ots/<date>.txt(.ots)    daily manifest + OTS proof;
                                                  Bitcoin-anchored weekly
    route B (weekly) ─▶ Data/esios_prices.json    independent deep history
                                                  (2015→), cross-checked vs A;
                                                  disagreement → CROSSCHECK-
                                                  ALERTS.log (committed, loud)
    everything ──▶ git ──▶ mirror ──▶ Pages dashboard + routines + auditors

## Strategy panel (registry in loop.STRATEGIES)

    persistence v1 (PRIMARY)  basis = yesterday's profile
    climatology v1 (shadow)   basis = per-hour mean of trailing 28 complete days
    rankblend  v1 (shadow)    basis = mean of the two legs' per-hour ranks
    weekly     v1 (shadow)    basis = same hour last week, p(d-7,h) — the EPF
                              literature's canonical naive (registered 08-22)
    Adding one = one registry entry + basis_fn. Promotion/retirement are
    mechanical (CLAUDE.md rules R1/R7). Settlement math never changes per
    strategy — comparability is the point. Live per-strategy P&L/capture is not
    frozen here — it lives in the ledger, `... status`, and the dashboards.

## Failure paths (designed, tested)

    fetch fails/insane   → retry, then stale-data tick; commitment may still
                           be legal (guard checks OUR dataset); honest miss
                           otherwise. NEVER a corrupted dataset.
    late tick            → leak guard refuses commit; missed day stands forever
    shell step fails     → logged, tick continues; missing heartbeat/email IS
                           the alarm (dead-man design)
    server dies          → Persistent=true catch-up on boot; monitor chain in
                           docs; restore drill proven from GitHub alone
    silent corruption    → weekly two-route cross-check + Monday auditor
                           recomputing everything from public data

## Automation & verification (updated 2026-08-27)

    Cloud routines (claude.ai, Gmail/push-notified):
      daily digest        ~16:35 UTC — ledger email
      Monday auditor      07:00 UTC  — fresh-context, READ-ONLY (never writes)
      Monday resolver     09:00 UTC  — fixes audit findings, auto-merges GREEN
                                       PRs (CI-gated), escalates gated items
      month-end review    1st 08:00 UTC
      gate reminder       one-time 2026-09-04 — GBM v2 override window closes
    CI (GitHub Actions, on push/PR):
      pytest -q  +  verify_ledger.py --all   (re-derives EVERY market's ledger;
                                              a discrepancy fails the build)
    Branch protection:  main-protection ruleset — force-push + deletion blocked.
    Independent re-derivation (anyone can run it):
      scripts/verify_ledger.py --all [--verify-ots]  — recomputes every
      settlement from raw prices + each receipt's own params (imports nothing
      from the package), re-checks the leak guard, proves append-only via the
      OTS-manifest prefix hashes, reports Bitcoin coverage. Tamper-tested
      (tests/test_verify_ledger.py). It runs in CI, and each PUBLIC mirror (ES,
      DE) runs it as its OWN workflow → the green "verify" badge in each mirror
      README is a live, anonymous check, not decoration. Private markets
      (IT/PT/ERCOT) are covered by the private CI's `--all`, not a public badge.

Deeper dives: VERIFY.md (outsider audit), docs/gate-analysis-plan.md
(evaluation), docs/evolution-plan.md (how it advances), docs/incidents.md
(what has actually broken), docs/BACKLOG.md (what's next).
