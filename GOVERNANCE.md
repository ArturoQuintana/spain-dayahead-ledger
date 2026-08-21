# Governance (public extract)

The full operating constitution lives in the private operations repo; this
extract contains every part an outside verifier needs. Nothing here may be
weakened by the operators; changes require the owner's written amendment,
before the data that would trigger them.

## Invariants

1. **Leak guard**: a receipt for target day T is committed only if no price
   for T exists in the project's dataset. A missed day is honest; a leaked
   receipt is worthless. Never bypassed, never backfilled.
2. **Append-only audit trail**: receipts and ledger are never edited,
   revised, or regenerated.
3. **Pre-registered strategies**: changing decision logic means a NEW
   strategy id/version on new receipts; old receipts stand forever
   (graveyard rule — retired strategies keep their settled history).
4. **Explicit costs**: P&L includes round-trip efficiency and fees; gross
   is never reported as net.

## Falsification (pre-registered stop conditions)

1. ≥90 settled days AND primary net P&L ≤ 0 → the premise is falsified;
   wind down or redesign openly.
2. Rolling 30-day mean capture < 70% for EVERY panel strategy → freeze all
   escalation; diagnose the regime change first.
3. If candidate models cannot beat the best pre-registered baseline BOTH
   out-of-sample (≥1-year temporal backtest) AND on ≥30 shared live shadow
   days → "our forecast adds sellable value" is falsified.

## Deciding strategy comparisons

"A beats B" requires, over SHARED settled days: ≥30 non-tied days AND
one-sided sign test p < 0.05 on paired daily P&L deltas (ties |Δ| < 0.01
EUR excluded). Below that bar, no superiority claims — anywhere.

## Independent verification roles

- A weekly fresh-context AUDITOR (read-only) extracts the public claims and
  verifies them against observable reality.
- A STATISTICAL REFEREE (fresh-context, read-only) must independently
  recompute every published statistical claim from the pre-registration
  documents and raw data before publication; a discrepancy blocks
  publication. The referee is barred from proposing method changes.
- The CLOSED DEFECT LOOP: every incident or audit finding must end as a
  detector or regression test for its class; the tracked metric is the
  escape rate (failures noticed by humans before machinery).
