# Data sources & licences

Talea publishes price-derived ledgers for several markets. Each market's **price
data** comes from that market's own source, under that source's terms; the licence
travels with the data in `Data/<slug>/LICENSE.md`. This file indexes them.

Only **redistributable** markets are published. Markets whose price data is not
freely redistributable (the ENTSO-E-sourced IT/PT/FR) are never included in this
public mirror.

| Market | Directory | Source | Licence / terms | Required attribution |
|--------|-----------|--------|-----------------|----------------------|
| Spain (ES) | `Data/es/` | REE — apidatos.ree.es | REE public data | Red Eléctrica de España (REE) |
| Germany (DE) | `Data/de/` | SMARD.de (Bundesnetzagentur) | CC BY 4.0 | Bundesnetzagentur \| SMARD.de |
| Great Britain (GB) | `Data/gb/` | Elexon BMRS Insights | Elexon open data | Elexon / BMRS |
| ERCOT | `Data/ercot/` | ERCOT MIS (NP4-190, DAM SPP) | ERCOT public data | ERCOT |

The **authoritative** terms are each source's own — see the per-market
`LICENSE.md` and the linked source for the binding conditions.

Ledger figures are **derived** metrics: the settlement of a simulated
1 MW / 2 MWh battery against these published prices. Talea claims no ownership of
the underlying price data. The Talea **code** (`src/`, `scripts/`, `tests/`) is
licensed separately — see `LICENSE`.
