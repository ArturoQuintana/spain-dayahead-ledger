# A committed-before-truth ledger for Spanish day-ahead power

[![verify](https://github.com/ArturoQuintana/spain-dayahead-ledger/actions/workflows/verify.yml/badge.svg)](https://github.com/ArturoQuintana/spain-dayahead-ledger/actions/workflows/verify.yml)

**Live dashboard:** see `index.html` (GitHub Pages) · **Audit it yourself:** [VERIFY.md](VERIFY.md)

The badge above is not decorative: GitHub re-runs `scripts/verify_ledger.py`
on this repository daily and on every update, independently re-deriving every
settlement from the raw prices and receipts. Green means the numbers reconcile;
you can run the identical command yourself (see [VERIFY.md](VERIFY.md)).

This repository is the public, auditable record of a paper-trading
experiment on Spanish day-ahead electricity prices (OMIE/ESIOS). Every day,
BEFORE the ~13:15 CET auction publication, a set of pre-registered
strategies commits receipts simulating a 1 MW / 2 MWh battery (buy the 2
cheapest hours, sell the 2 dearest; 85% round-trip efficiency; explicit
fees). Settlements against the published prices are appended to a ledger
that is never edited.

What makes this record different from a backtest or a vendor claim:

- **Committed before truth**: a receipt for day T exists only if it was
  recorded before T's prices were published — enforced in code (the leak
  guard) and provable from the outside.
- **Tamper-evident**: daily OpenTimestamps proofs anchor the audit files'
  hashes in Bitcoin (`Data/ots/`). You do not need to trust us, or GitHub.
- **Append-only, losses included**: missed days and losing days stay in the
  record forever. Strategy changes require a new pre-registered strategy id.
- **Pre-registered stop conditions and comparison tests**: the conditions
  under which this experiment is WRONG were published before the data that
  could trigger them.

Metrics reported: money net of costs; **capture** (realized P&L ÷
perfect-hindsight P&L, same battery, same costs); **Kendall tau** (rank
quality of each committed forecast); regime telemetry (negative-price
hours, top-bottom-2 spread).

Honesty note: absolute EUR is an upper bound — fees cover the exchange
only, not grid charges, taxes, or aggregator margin. Relative metrics are
robust to this. Prices come from the public apidatos.ree.es API,
cross-checked weekly against the independent token-based ESIOS route.

Reproduce everything: `uv sync && uv run pytest` (the settlement math is
pure functions), then follow [VERIFY.md](VERIFY.md).
