# GBM v2 gate — verdict (2026-08-21)

Evaluated on the 21st settled day, per the pre-registered analysis plan
(docs/gate-analysis-plan.md, committed 2026-08-20 before the data existed).
Independently recomputed by the statistical referee (fresh-context,
read-only): **CONFIRMED** — every figure matched to 4 decimals.

## Numbers

- Settled days (primary, persistence v1): **21** (2026-07-31 → 2026-08-22),
  21/21 wins, +6,075.94 EUR of 6,283.09 oracle.
- **Pooled capture: 0.9670.** Mean-of-daily (secondary): 0.9617.
- **Trend: +0.0227** (first-10 pooled 0.9575 → last-10 pooled 0.9802).
  Rising, not falling.
- Tau (13 instrumented days): mean 0.839.

## Band and consequence

Pooled 0.9670 ≥ 0.92 and trend ≥ −0.03 → the plan's **"holding" band**:
building v2 is a conscious user choice, not a mechanical consequence.
Under rule R2 the pre-registered default applies: **DO NOT BUILD; the loop
continues unchanged. The user may override within 14 days (until
2026-09-04).**

## Mandatory context (cannot change the verdict)

- **Seasonal caveat**: all 21 days are August solar-regime days. The 11.5y
  backtest puts winter (DJF) persistence capture at 64–75% pooled — this
  sample cannot speak for winter, and the gate's "holding" reading is
  summer-conditional.
- **Panel**: climatology vs primary +4.32 EUR over 18 shared (p=0.50);
  rankblend vs primary +28.71 EUR over 11 shared (p=0.34). No comparison
  near the pre-registered bar. Rolling-30 capture: pers 0.962, clim 0.975,
  blend 0.982.
- **Falsification checks**: none triggered (21 < 90 days for F1; all
  strategies far above 0.70 for F2; F3 not yet applicable — no v2 exists).
- **Path-(b) framing** (on record since 2026-08-01): under
  sell-the-forecast, high persistence capture does not argue against
  building — the sellable asset is the margin over the best baseline. The
  recoverable margin is concentrated in winter (backtest: 17–25 EUR/day DJF
  vs ~6 in the current regime). A user override toward BUILD would be
  consistent with the recorded monetization path; the default merely
  refuses to make that call mechanically.

## What executes now (freeze lifted)

Clock-deadline guard, weekly-naive shadow registration, CI + protected
main, and the queued post-gate builds — per docs/BACKLOG.md.
