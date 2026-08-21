# Pre-registered analysis plan for the GBM v2 gate
(committed 2026-08-20 evening, BEFORE the 21st settled day exists; the gate
criteria themselves were frozen 2026-08-21-minus-weeks in CLAUDE.md — this
plan fixes their COMPUTATION so the evaluator has no residual discretion)

## Inputs
All persistence-v1 settled days in Data/ledger.jsonl at evaluation time
(expected 21). Shadows and the 11.5y backtest are context, not criteria.

## Primary computations (exact)
1. **Capture level** = POOLED capture: sum(pnl_eur) / sum(oracle_pnl_eur)
   over all settled days. (Pooled, not mean-of-ratios: our backtest showed
   mean-of-daily-ratios explodes on near-zero-oracle days. Mean-of-daily is
   reported as a secondary figure only.)
2. **Trend** = pooled capture over the LAST 10 settled days minus pooled
   capture over the FIRST 10 settled days. "Trending down" := this
   difference < -0.03 (three points).

## Criteria mapping (from the frozen gate text)
- "< ~90% or trending down -> build": pooled capture < 0.90 OR trend
  < -0.03 => BUILD v2 (harness first, model second; shadow receipts as
  strategy_version 2). Unambiguous -> M4 executes.
- "holding ~93% -> conscious user choice": pooled capture >= 0.92 and trend
  >= -0.03 => present numbers to the user WITH the path-(b) framing
  (memory: monetization-path) and the backtest's seasonal caveat; the
  build/no-build decision is the USER'S. Agent stops.
- Between 0.90 and 0.92: treated as the discretionary zone -> user decides.

## Mandatory context in the verdict (cannot change the verdict)
- Seasonal caveat: the sample is entirely August (solar regime); backtest
  DJF pooled capture for persistence is 64-75% — the verdict must state the
  sample cannot speak for winter.
- Panel standing: pooled capture + tau for climatology and rankblend on
  shared days; sign-test standings vs the pre-registered bar.
- Falsification criteria check (all three; report pass/fail plainly).
- The path-(b) note: under sell-the-forecast, beating the BEST baseline is
  the entry ticket regardless of capture level.

## Publication
Verdict + all numbers committed to docs/gate-verdict-2026-08.md the same
night; digest email carries the one-line verdict; user report in session.
