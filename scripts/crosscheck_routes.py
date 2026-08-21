"""Cross-validate the two independent price routes over the trailing window.

Route A: Data/prices.json (tokenless apidatos.ree.es — the loop's dataset of
record). Route B: Data/esios_prices.json (token api.esios.ree.es, refreshed by
the weekly maintenance job). Both derive from the same OMIE auction, so any
disagreement beyond rounding means one feed is broken — the ledger's only
remaining silent-corruption channel.

Only 24-hour days are compared (route B stores DST days as dense lists).
Exit 0 = agree; exit 1 = mismatch (details on stdout).

Run: uv run python scripts/crosscheck_routes.py [days=14] [tolerance=0.51]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "Data"


def main() -> int:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    tol = float(sys.argv[2]) if len(sys.argv) > 2 else 0.51

    route_a: dict[str, dict[int, float]] = {}
    for row in json.loads((DATA / "prices.json").read_text()):
        d, h = row["ts"].split("T")
        route_a.setdefault(d, {})[int(h)] = row["price"]

    route_b = {}
    for row in json.loads((DATA / "esios_prices.json").read_text()):
        d = datetime.strptime(row["date"], "%d/%m/%Y").date().isoformat()
        route_b[d] = row["prices"]

    cutoff = (datetime.now().date() - timedelta(days=days_back)).isoformat()
    shared = sorted(d for d in route_a
                    if d >= cutoff and d in route_b
                    and len(route_a[d]) == 24 and len(route_b[d]) == 24)
    if len(shared) < 3:
        print(f"CROSSCHECK INCONCLUSIVE: only {len(shared)} shared complete "
              f"days in trailing {days_back} (route B stale?)")
        return 1

    bad = []
    for d in shared:
        for h in range(24):
            diff = abs(route_a[d][h] - route_b[d][h])
            if diff > tol:
                bad.append((d, h, route_a[d][h], route_b[d][h], round(diff, 3)))
    if bad:
        print(f"CROSSCHECK FAILED: {len(bad)} hour(s) disagree beyond "
              f"{tol} EUR/MWh across {len(shared)} shared days:")
        for row in bad[:20]:
            print("  ", row)
        return 1
    print(f"crosscheck ok: {len(shared)} days x 24h agree within {tol} EUR/MWh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
