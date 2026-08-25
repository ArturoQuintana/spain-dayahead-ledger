# Verified-track-record products across domains: findings + design mandates
(deep-research run 2026-08-20; 106 agents, all findings 2-3 vote adversarially
verified; primary sources incl. founder postmortems and peer-reviewed papers)

One-sentence thesis: **the credible products delegate verification to data the
measured party cannot edit, commit before truth against explicit naive
baselines, and score money — and the failures die from biased enrollment
(backfill/survivorship) or from acceptance filters that manufacture overfit
signal, not from weak cryptography.**

## Findings (all high-confidence)

1. **Myfxbook (retail forex, the volume leader)** verifies by *delegation to
   the broker's feed* + a separate account-ownership challenge; public
   sharing is gated on both. Trust bottoms out at the broker (demo-relabel
   and complicit-broker gaming exist). Our OTS/Bitcoin anchoring is strictly
   stronger — no trusted intermediary at all. COPY their two-proof split:
   attest WHAT was submitted and WHO controls the submitting identity as
   separate proofs.
2. **Hedge-fund databases (BarclayHedge/HFR)** structurally inflate ~4-5%/yr
   via backfill bias (flattering pre-listing history imported at opt-in) and
   ~1.4-4%/yr via survivorship (losers opt out). MANDATES: no backfill ever
   (a record starts at its first pre-committed receipt) and the **graveyard
   rule** — a lapsed strategy's settled history is never deleted.
3. **QuantConnect Alpha Streams — the key postmortem (died Feb 2022)**:
   verification was genuinely strong (platform-side live execution,
   millisecond timestamps) and the product still died, by the founder's own
   admission, because the acceptance filter ("perform well in all regimes")
   *selected for overfitting* — verified records of worthless signal sell
   nothing. MANDATES: no curatorial acceptance filter — open rail, baselines
   and pre-registered bars do the sorting; disclose plainly (VERIFY.md) that
   records are paper/signal, and that "independent" means independent of the
   VENDOR while we operate the rail (OTS is the mitigation).
4. **Numerai staking**: optional skin-in-the-game done right — unstaked
   submissions build a free, identically-scored paper record; the stake (not
   the leaderboard) gates meta-model weight; burned stakes are destroyed,
   not captured by the house (caveat: treasury holdings benefit indirectly —
   disclose equivalents if we ever add staking). TEMPLATE: free tier =
   attested scorecard; economic weight/monetization = the gated tier.
5. **M6 live competition base rates** (163 teams, 12 months, peer-reviewed):
   23% beat the naive forecast benchmark, 29% beat the investment benchmark,
   **6.7% beat both**; 3/163 beat forecasts every month, 0/163 beat
   decisions every month. Accuracy-rank vs money-rank R² = 0.099 — the
   strongest external vindication of our P&L/capture-first metrics.
   EXPECTATION-SETTING: most rail tenants will NOT beat baselines; that is
   the product working. Our >=30-day bars are floors, not targets.
6. **M-competitions governance**: settle disputes by empirical performance
   (explicit charter), and M5's dual-track scoring (point accuracy AND
   uncertainty via pinball loss) institutionalized distributional
   evaluation. ADD: an uncertainty track (quantile submissions scored by
   pinball/CRPS) alongside P&L and capture in the rail's scorecards.
7. **Metaculus** shows what a trusted track-record page looks like: the
   public aggregate page SHIPS the complete per-question raw dataset in its
   own payload (12,103 records, independently re-checkable), pre-defined
   uncertainty-aware calibration methodology, and scoring reforms (Baseline/
   Peer scores) that replaced a gameable points system; hidden periods
   counter herding. COPY: radical raw-data-in-the-page auditability (we are
   close — link the jsonl from the dashboard explicitly); hidden submission
   windows per tenant; baseline-relative scores as the headline number.

## Design mandates for the attestation-rail MVP (~Sep-Oct 2026)

- **No backfill; graveyard rule** — enrollment starts at first attested
  receipt, exits never erase settled history. (Bias findings 2.)
- **No acceptance filter** — open enrollment; the baselines, bars, and
  base-rate context do the sorting. (Alpha Streams 3.)
- **Two-proof attestation** — content proof (OTS on the submission hash) +
  identity proof (submitting key/token ownership), reported separately. (1.)
- **Headline scores are baseline-relative and money-denominated**; publish
  M6-style base rates on the leaderboard so "most don't beat naive" reads as
  honesty, not failure. (5, 7.)
- **Uncertainty track from day one of the rail spec** (quantiles + pinball),
  even if v1 accepts point forecasts only. (6.)
- **Free paper tier forever; monetize the gated tier** (badges, private
  scorecards, evaluations; staking optional and only later, with operator-
  interest disclosure). (4.)
- **Radical auditability**: dashboard links the raw audit files; VERIFY.md
  gains the paper-vs-real and operator-role disclosures. (3, 7.)
- **Hidden submission windows** for multi-tenant days (no seeing others'
  forecasts pre-deadline). (7.)
