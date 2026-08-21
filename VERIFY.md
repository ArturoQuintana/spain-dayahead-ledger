# How to verify this ledger (for a skeptic)

The claim: every trading decision in `Data/receipts.jsonl` was committed
BEFORE the prices it would be judged against were published, and every P&L
figure in `Data/ledger.jsonl` follows mechanically from those receipts and
publicly available prices. You should not have to trust us on any of it.

## 1. The timing claim (receipts predate the auction)

The Spanish day-ahead auction publishes prices for delivery day T at ~13:15
CET on T-1. A receipt for target T is honest only if it existed before that.

**Weak check (trusts GitHub):** every tick commits and pushes `Data/`. Compare
any receipt's `committed_at` (UTC, inside the file) with the push time of the
commit that introduced it: `git log --follow --format='%H %cI' -- Data/receipts.jsonl`.

**Strong check (trusts no one):** `Data/ots/<date>.txt` holds the SHA-256 of
both audit files at stamp time; `<date>.txt.ots` is an OpenTimestamps proof
anchoring that manifest in Bitcoin. Verify with the open-source client:

    sha256sum Data/receipts.jsonl        # compare against the manifest text
    ots verify Data/ots/<date>.txt.ots   # proves the manifest existed at time X

(Proofs are stamped daily and upgraded to Bitcoin-anchored weekly; a
just-created proof may still be "pending" — re-run `ots upgrade` later.)

**Evidence boundaries, stated plainly.** This public mirror was created on
2026-08-10: days before that date entered it in one bulk commit, so the
"weak check" above cannot corroborate them from this repository alone (the
private operations repository holds their per-tick commit history, shown on
request). OTS attestation begins 2026-08-08; the first week (2026-07-30 →
2026-08-07) has no Bitcoin anchoring and cannot acquire it retroactively —
timestamps cannot be backdated, which is the entire point of the mechanism.
Treat the record as three tiers of strength: OTS-anchored (2026-08-08+),
git-corroborated (private repo, 2026-07-30+), and the mirror's own history
(2026-08-10+). On 2026-08-21 an independent audit found that same-day
re-ticks had been silently rewriting stamped manifests, invalidating 12
proofs; the stamped originals were restored from git history (every proof
now matches), the tick was fixed so stamped manifests are immutable
(changed state gets a new suffixed manifest), and a regression test pins
the class. Data/esios_prices.json (the independent cross-check route)
updates WEEKLY by design — staleness under 7 days is normal.

## 2. The arithmetic claim (P&L follows from receipts + public prices)

Prices are public: apidatos.ree.es (no key) or api.esios.ree.es (free key),
both derived from the OMIE auction. For any settled day:

    pnl = sum(price[h] for h in sell_hours) * 1.0 MW * 0.85
        - sum(price[h] for h in buy_hours) * 1.0 MW
        - 0.5 EUR/MWh * (2 * 1.0 + 2 * 0.85)        # fees on energy moved

The oracle is the same formula over the day's 2 cheapest / 2 dearest hours;
capture = pnl / oracle_pnl. The exact code is `src/esios_paper/loop.py`
(pure functions, unit-tested: `uv run pytest`). The independent second price
route is cross-checked weekly (`scripts/crosscheck_routes.py`).

## 3. The no-cherry-picking claim

Both audit files are append-only: every receipt ever committed has a
settlement or a documented missed day. MISSED days stay in the record
(2026-08-05 and 2026-08-07 are real examples). LOSING days will stay
identically when they occur — as of 2026-08-21 the primary has none in 21
settled days, a fact we flag rather than celebrate: the sample is one
solar-heavy August, and our own 11.5-year backtest says winter brings
losing days. Strategy changes require a new
pre-registered strategy id; old receipts stand. Stop conditions and the
comparison bar are pre-registered in GOVERNANCE.md (the public extract of
the operating constitution); strategy-vs-strategy claims must clear that
bar (`scripts/compare_strategies.py` in this repository).

## 4. What this ledger does NOT claim

Paper trading — no market participation, execution assumed at the clearing
price (realistic for 1 MW, a price-taker). The 0.5 EUR/MWh fee covers
exchange fees only: no grid charges, taxes, or aggregator margin, so absolute
EUR is an upper bound on what a real asset would net. Relative metrics
(capture, tau, strategy deltas) are robust to that. Hourly frame; the market
itself clears at 15-minute granularity since 2025-10-01.

Two disclosures the verified-track-record industry has taught us to make
explicitly (see docs/research-track-records-2026-08.md): these are SIGNAL
records, not real-money execution records — the distinction that
QuantConnect's Alpha Streams glossed and later regretted. And "independent"
here means independent of the STRATEGY (nothing can be revised after
commitment); the ledger is operated by the project itself — the
OpenTimestamps anchoring exists precisely so that operator role never has to
be taken on trust. Two structural guarantees follow from the same industry's
failure modes: records never start before their first pre-committed receipt
(no backfill), and a retired strategy's settled history is never removed
(no survivorship laundering).
