# The Spanish (ES) ledger moved to `Data/es/`

On **2026-08-28** the Spanish day-ahead ledger moved from this directory's root to
**`Data/es/`**, so that every market — ES included — lives symmetrically under
`Data/<slug>/` and no market is privileged at the project root. `Data/` root now
holds only shared/project artifacts and one subdirectory per market.

**If you had a link to the old paths, use these instead:**

| Old | New |
|---|---|
| `Data/receipts.jsonl` | `Data/es/receipts.jsonl` |
| `Data/ledger.jsonl` | `Data/es/ledger.jsonl` |
| `Data/prices.json` | `Data/es/prices.json` |
| `Data/ots/` | `Data/es/ots/` |

**Nothing about the record changed.** The move is a content-preserving `git`
rename: every receipt is byte-identical, the git history is preserved, and the
OpenTimestamps proofs still validate (they anchor the file *content* hash with a
relative filename, both unaffected by the move). You can confirm this yourself:

```
python scripts/verify_ledger.py --all --verify-ots
```

The append-only audit trail is intact — a relocation is not a rewrite.
