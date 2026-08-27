"""Render the public ledger dashboard (static index.html) from Data/.

Everything is computed from the audit files — no hand-maintained numbers.
Run after each tick (server) or manually:
    uv run python scripts/render_dashboard.py [out_path]
Default out: site/index.html (the mirror publishes it via GitHub Pages).
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data"
PRIMARY = "battery-2h2h-persistence"
NAMES = {"battery-2h2h-persistence": "Persistence v1",
         "battery-2h2h-climatology": "Climatology v1",
         "battery-2h2h-rankblend": "Rank-blend v1",
         "battery-2h2h-weekly": "Weekly v1"}
GATE_DAYS = 21

# Per-market presentation. ES is the default and keeps the public page
# byte-identical; other markets override the labels and drop the ES-only gate.
MARKETS = {
    "es": {"data": DATA, "title": "Iberian (MIBEL) day-ahead battery arbitrage",
           "tzlabel": "Madrid", "gate": True,
           "source": "apidatos.ree.es (Spanish/ES zone; under MIBEL, "
                     "Portuguese/PT prices match except on rare congestion "
                     "splits),\n      cross-checked weekly against the "
                     "independent token ESIOS route"},
    "de": {"data": DATA / "de", "title": "German (DE-LU) day-ahead battery arbitrage",
           "tzlabel": "Berlin", "gate": False,
           "source": "Bundesnetzagentur | SMARD.de (CC BY 4.0)"},
    "it": {"data": DATA / "it", "title": "Italian (IT-SUD) day-ahead battery arbitrage",
           "tzlabel": "Rome", "gate": False,
           "source": "ENTSO-E (private use; prices not redistributed)"},
}


def jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def day_curves(data: Path = DATA) -> dict[str, list[float | None]]:
    by: dict[str, dict[int, float]] = {}
    for r in json.loads((data / "prices.json").read_text()):
        d, h = r["ts"].split("T")
        by.setdefault(d, {})[int(h)] = r["price"]
    return {d: [v.get(h) for h in range(24)] for d, v in by.items()}


def fmt(x: float) -> str:
    return f"{x:,.2f}"


def build(slug: str = "es") -> str:
    cfg = MARKETS[slug]
    DATA = cfg["data"]
    ledger = jsonl(DATA / "ledger.jsonl")
    receipts = jsonl(DATA / "receipts.jsonl")
    curves = day_curves(DATA)
    now = datetime.now(ZoneInfo("Europe/Madrid"))

    prim = [e for e in ledger if e["strategy"] == PRIMARY]
    prim_by_day = {e["target"]: e for e in prim}
    total = sum(e["pnl_eur"] for e in prim)
    oracle_total = sum(e["oracle_pnl_eur"] for e in prim)
    caps = [e["capture"] for e in prim if e.get("capture") is not None]
    cap_mean = statistics.fmean(caps) * 100 if caps else 0
    wins = sum(1 for e in prim if e["pnl_eur"] > 0)

    # missed primary days: dates in [first receipt target, last settled target]
    # with no primary receipt at all
    prim_receipts = {r["target"] for r in receipts if r["strategy"] == PRIMARY}
    d0 = date.fromisoformat(min(prim_receipts))
    d1 = date.fromisoformat(max(e["target"] for e in prim))
    missed = []
    d = d0
    while d <= d1:
        if d.isoformat() not in prim_receipts:
            missed.append(d.isoformat())
        d += timedelta(days=1)

    settled_keys = {(e["target"], e["strategy"]) for e in ledger}
    open_receipts = [r for r in receipts
                     if (r["target"], r["strategy"]) not in settled_keys]

    # day cards for the primary (curve + basis curve joined from receipts)
    prim_receipt_by_target = {r["target"]: r for r in receipts
                              if r["strategy"] == PRIMARY}
    days_js = []
    for e in prim:
        t = e["target"]
        rec = prim_receipt_by_target.get(t, {})
        basis_day = rec.get("basis_day")
        if t not in curves or basis_day not in curves:
            continue
        if any(v is None for v in curves[t] + curves[basis_day]):
            continue
        days_js.append({
            "target": t,
            "weekday": date.fromisoformat(t).strftime("%A"),
            "buy": e["buy_hours"], "sell": e["sell_hours"],
            "pnl": e["pnl_eur"], "oracle": e["oracle_pnl_eur"],
            "capture": e["capture"], "tau": e.get("tau"),
            "prices": curves[t], "basis": curves[basis_day],
            "basisDate": basis_day,
        })

    # head-to-head: one row per settled day, one cell per strategy
    strategies = [s for s in NAMES if any(e["strategy"] == s for e in ledger)]
    by_day: dict[str, dict[str, dict]] = {}
    for e in ledger:
        by_day.setdefault(e["target"], {})[e["strategy"]] = e
    h2h_rows = []
    for t in sorted(set(list(by_day) + missed)):
        cells = []
        for s in strategies:
            e = by_day.get(t, {}).get(s)
            if e is None:
                cells.append("<td>missed</td>" if s == PRIMARY and t in missed
                             else "<td>—</td>")
            else:
                cap = (f"{e['capture'] * 100:.1f}%"
                       if e.get("capture") is not None else "n/a")
                tau = (f" · tau {e['tau']:.3f}"
                       if e.get("tau") is not None else "")
                cells.append(f"<td>+{fmt(e['pnl_eur'])}&thinsp;€ ({cap}{tau})"
                             "</td>")
        h2h_rows.append(f'<tr><td class="k">{t}</td>{"".join(cells)}</tr>')
    # pairwise totals vs primary on shared days
    pair_notes = []
    for s in strategies:
        if s == PRIMARY:
            continue
        shared = [(by_day[t][s]["pnl_eur"], by_day[t][PRIMARY]["pnl_eur"])
                  for t in by_day if s in by_day[t] and PRIMARY in by_day[t]]
        if shared:
            delta = sum(a - b for a, b in shared)
            pair_notes.append(f"{NAMES[s]} vs {NAMES[PRIMARY]}: "
                              f"{delta:+.2f}&thinsp;€ over {len(shared)} "
                              "shared days")
    h2h_head = "".join(f"<th>{NAMES[s]}{' · primary' if s == PRIMARY else ' · shadow'}</th>"
                       for s in strategies)

    ledger_rows = []
    for e in prim:
        buy_avg = statistics.fmean(e["buy_prices"])
        sell_avg = statistics.fmean(e["sell_prices"])
        cap = (f"{e['capture'] * 100:.1f}%"
               if e.get("capture") is not None else "n/a")
        ledger_rows.append(
            f'<tr><td class="k">{e["target"]}</td>'
            f'<td>{", ".join(f"{h:02d}" for h in e["buy_hours"])}</td>'
            f"<td>{fmt(buy_avg)}</td>"
            f'<td>{", ".join(f"{h:02d}" for h in e["sell_hours"])}</td>'
            f"<td>{fmt(sell_avg)}</td>"
            f'<td class="pos">+{fmt(e["pnl_eur"])}</td>'
            f"<td>{fmt(e['oracle_pnl_eur'])}</td><td>{cap}</td></tr>")
    for m in missed:
        ledger_rows.append(
            f'<tr><td class="k">{m}</td><td colspan="6" style="text-align:'
            'left">missed — no receipt committed before the window closed; '
            "never backfilled (leak guard)</td><td>—</td></tr>")

    open_html = []
    for r in open_receipts:
        open_html.append(
            f'<div class="open-card" style="margin-bottom:10px">'
            f'<span class="pending">Pending</span>'
            f'<span class="oc"><b>{r["target"]}</b> · {NAMES.get(r["strategy"], r["strategy"])}'
            f'{" · primary" if r["strategy"] == PRIMARY else " · shadow"}</span>'
            f'<span class="oc">buy <b class="m">{"·".join(f"{h:02d}" for h in r["buy_hours"])}h</b>'
            f' · sell <b class="m">{"·".join(f"{h:02d}" for h in r["sell_hours"])}h</b></span>'
            f'<span class="oc">committed <span class="m">{r["committed_at"][:16]}Z</span>,'
            f' before publication</span></div>')
    if not open_html:
        open_html = ['<div class="open-card"><span class="pending">None open'
                     '</span><span class="oc">Next commit at the next 11:00 '
                     'Europe/Madrid tick.</span></div>']

    if cfg["gate"]:
        gate_cells = "".join(f'<i class="{"done" if i < len(prim) else ""}"></i>'
                             for i in range(GATE_DAYS))
        gate_tile = (
            '<div class="tile"><div class="k">GBM v2 gate</div>'
            f'<div class="v">{min(len(prim), GATE_DAYS)} / {GATE_DAYS}</div>'
            '<div class="s">settled days · evaluate ~21 Aug</div></div>')
        gate_section = (
            '<h2>Escalation gate</h2><div class="gate">'
            '<div class="gl"><span>Progress to the GBM&nbsp;v2 evaluation</span>'
            f'<span class="m">{min(len(prim), GATE_DAYS)} of {GATE_DAYS} settled days</span></div>'
            f'<div class="gate-cells">{gate_cells}</div>'
            '<div class="gl"><span>Evaluation criteria frozen in advance; stop '
            'conditions pre-registered</span><span class="m">~21 Aug 2026</span></div></div>')
    else:
        gate_tile = (
            '<div class="tile"><div class="k">Market</div>'
            f'<div class="v">{slug.upper()}</div>'
            '<div class="s">silent shadow ledger</div></div>')
        gate_section = ""

    return TEMPLATE % {
        "tabtitle": {"es": "Iberia", "de": "Germany", "it": "Italy"}[slug]
                    + " day-ahead ledger",
        "title": cfg["title"],
        "source": cfg.get("source", "apidatos.ree.es"),
        "asof": now.strftime(f"%Y-%m-%d %H:%M {cfg['tzlabel']}"),
        "total": fmt(total), "oracle_total": fmt(oracle_total),
        "cap_mean": f"{cap_mean:.1f}", "wins": wins, "n": len(prim),
        "missed_n": len(missed),
        "gate_tile": gate_tile, "gate_section": gate_section,
        "days_json": json.dumps(days_js),
        "open_cards": "\n".join(open_html),
        "h2h_head": h2h_head, "h2h_rows": "\n".join(h2h_rows),
        "pair_notes": " · ".join(pair_notes) or "no shared shadow days yet",
        "n_strategies": len(strategies),
        "ledger_rows": "\n".join(ledger_rows),
    }


TEMPLATE = """<title>%(tabtitle)s</title>
<style>
  :root { color-scheme: light;
    --bg:#f9f9f7; --card:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
    --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7;
    --border:rgba(11,11,11,.10); --buy:#2a78d6; --sell:#eb6834;
    --good:#006300; --bad:#d03b3b;
    --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace; }
  @media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) {
    color-scheme:dark; --bg:#0d0d0d; --card:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --buy:#3987e5; --sell:#d95926; --good:#0ca30c; } }
  :root[data-theme="dark"] {
    color-scheme:dark; --bg:#0d0d0d; --card:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --buy:#3987e5; --sell:#d95926; --good:#0ca30c; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 var(--sans); }
  .wrap { max-width:940px; margin:0 auto; padding:40px 20px 56px; }
  .eyebrow { font:600 11px/1 var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
  h1 { font:600 26px/1.25 var(--sans); margin:8px 0 4px; text-wrap:balance; }
  .asof { color:var(--ink2); font-size:13.5px; margin:0; }
  .asof code { font-family:var(--mono); font-size:12.5px; }
  h2 { font:600 12px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase;
    color:var(--ink2); margin:40px 0 14px; display:flex; align-items:center; gap:12px; }
  h2::after { content:""; flex:1; height:1px; background:var(--grid); }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin-top:26px; }
  .tile { background:var(--card); border:1px solid var(--border); border-radius:6px; padding:14px 16px 12px; }
  .tile .k { font:600 10.5px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }
  .tile .v { font:600 27px/1.15 var(--sans); margin-top:7px; }
  .tile .v.pos { color:var(--good); }
  .tile .s { color:var(--ink2); font-size:12.5px; margin-top:3px; }
  .day { background:var(--card); border:1px solid var(--border); border-radius:6px;
    padding:18px 18px 12px; margin-bottom:16px; }
  .day-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 14px; margin-bottom:4px; }
  .day-head .date { font-weight:600; font-size:16px; }
  .day-head .wd { color:var(--muted); font-size:13px; }
  .chips { margin-left:auto; display:flex; gap:8px; }
  .chip { font:500 12.5px/1 var(--mono); padding:5px 9px; border-radius:99px;
    border:1px solid var(--border); color:var(--ink2); white-space:nowrap; }
  .chip.pnl-pos { color:var(--good); border-color:color-mix(in srgb,var(--good) 35%%,transparent); }
  .chip.pnl-neg { color:var(--bad); border-color:color-mix(in srgb,var(--bad) 35%%,transparent); }
  .day-sub { color:var(--ink2); font-size:13px; margin:0 0 10px; }
  .day-sub .m { font-family:var(--mono); font-size:12px; }
  .legend { display:flex; flex-wrap:wrap; gap:6px 18px; margin:2px 0 24px; align-items:center; }
  .legend .li { display:inline-flex; align-items:center; gap:7px; font-size:12.5px; color:var(--ink2); }
  .chart-box { position:relative; }
  .chart-box svg { display:block; width:100%%; height:auto; }
  .tip { position:absolute; pointer-events:none; display:none; background:var(--card);
    border:1px solid var(--border); border-radius:5px; box-shadow:0 2px 10px rgba(0,0,0,.14);
    font:500 12px/1.5 var(--mono); color:var(--ink); padding:7px 10px; white-space:nowrap; z-index:3; }
  .tip .t2 { color:var(--ink2); }
  .open-card { background:var(--card); border:1px solid var(--border); border-radius:6px;
    padding:16px 18px; display:flex; flex-wrap:wrap; gap:10px 26px; align-items:baseline; }
  .open-card .oc { font-size:13.5px; color:var(--ink2); }
  .open-card .oc b { color:var(--ink); font-weight:600; }
  .open-card .oc .m { font-family:var(--mono); font-size:12.5px; }
  .pending { font:600 10.5px/1 var(--mono); letter-spacing:.1em; text-transform:uppercase;
    color:var(--ink2); border:1px solid var(--axis); border-radius:99px; padding:5px 9px; }
  .note { color:var(--ink2); font-size:13px; margin:10px 2px 0; }
  .gate { background:var(--card); border:1px solid var(--border); border-radius:6px; padding:16px 18px; }
  .gate-cells { display:grid; grid-template-columns:repeat(21,1fr); gap:4px; margin:10px 0 8px; }
  .gate-cells i { display:block; height:14px; border-radius:3px; background:var(--bg); border:1px solid var(--grid); }
  .gate-cells i.done { background:var(--buy); border-color:var(--buy); }
  .gate .gl { display:flex; justify-content:space-between; color:var(--ink2); font-size:12.5px; }
  .gate .gl .m { font-family:var(--mono); font-size:12px; }
  .tbl-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:6px; background:var(--card); }
  table { border-collapse:collapse; width:100%%; min-width:640px; font-size:13px; }
  th, td { text-align:right; padding:9px 14px; border-top:1px solid var(--grid); white-space:nowrap; }
  th { border-top:0; font:600 10.5px/1 var(--mono); letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }
  th:first-child, td:first-child { text-align:left; }
  td { font-family:var(--mono); font-size:12.5px; font-variant-numeric:tabular-nums; color:var(--ink2); }
  td.k { color:var(--ink); }
  td.pos { color:var(--good); }
  tfoot td { border-top:2px solid var(--axis); font-weight:600; color:var(--ink); }
  footer { margin-top:44px; color:var(--muted); font-size:12.5px; line-height:1.7; }
  footer .m { font-family:var(--mono); font-size:11.5px; }
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">esios-paper · paper-trading ledger</p>
    <h1>%(title)s</h1>
    <p class="asof">1 MW / 2 MWh virtual battery · decisions committed before price publication
      (leak-guarded, OpenTimestamps-anchored) · data as of <code>%(asof)s</code> ·
      generated from the audit files, no hand-edited numbers</p>
  </header>

  <div class="tiles">
    <div class="tile"><div class="k">Net P&amp;L · paper</div>
      <div class="v pos">+%(total)s&thinsp;€</div>
      <div class="s">of %(oracle_total)s&thinsp;€ oracle ceiling</div></div>
    <div class="tile"><div class="k">Mean capture</div>
      <div class="v">%(cap_mean)s%%</div>
      <div class="s">of perfect-hindsight P&amp;L</div></div>
    <div class="tile"><div class="k">Record</div>
      <div class="v">%(wins)s / %(n)s</div>
      <div class="s">winning settled days · %(missed_n)s missed</div></div>
    %(gate_tile)s
  </div>

  <h2>Settled days · primary strategy</h2>
  <div class="legend" id="legend"></div>
  <div id="days"></div>

  <h2>Open receipts</h2>
  %(open_cards)s

  <h2>Strategy panel · identical settled days</h2>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Target day</th>%(h2h_head)s</tr></thead>
    <tbody>%(h2h_rows)s</tbody>
  </table></div>
  <p class="note">%(pair_notes)s. Claims of superiority require the
    pre-registered bar (&ge;30 non-tied shared days, sign-test p&lt;0.05) —
    see VERIFY.md. All %(n_strategies)s strategies settle on identical days
    with identical costs; none can be revised after the fact.</p>

  %(gate_section)s

  <h2>Ledger · append-only · primary</h2>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Target day</th><th>Buy hours</th><th>Buy avg</th>
      <th>Sell hours</th><th>Sell avg</th><th>P&amp;L</th><th>Oracle</th>
      <th>Capture</th></tr></thead>
    <tbody>%(ledger_rows)s</tbody>
  </table></div>

  <footer>
    <p>Costs are explicit in every figure: 85%% round-trip efficiency and
      0.50&thinsp;€/MWh fees on every MWh moved — net is never reported as
      gross. The oracle is the best possible 2×2 hour choice with hindsight,
      same battery, same costs. Capture = P&amp;L ÷ oracle P&amp;L; tau =
      Kendall tau-b of the committed forecast vs the actual day.</p>
    <p>Paper money — no capital at stake. Every receipt is committed and
      pushed before the D+1 auction publishes (~13:15 CET); the ledger is
      append-only and OpenTimestamps-anchored; prices: %(source)s.
      Absolute EUR is an <b>upper bound</b> (exchange fees only — no grid
      charges, taxes, or aggregator margin); relative metrics are robust.
      Verify everything yourself: see VERIFY.md in this repository.</p>
  </footer>
</div>

<script>
  const DAYS = %(days_json)s;
  const fmt = (x, d = 2) => x.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const avg = a => a.reduce((s, x) => s + x, 0) / a.length;
  const hh = h => String(h).padStart(2, "0");
  function oraclePicks(p) {
    const idx = p.map((v, i) => i);
    return { cheap: [...idx].sort((a, b) => p[a] - p[b]).slice(0, 2),
             dear:  [...idx].sort((a, b) => p[b] - p[a]).slice(0, 2) };
  }
  const YMAXBASE = 210;
  const YMAX = Math.max(YMAXBASE, ...DAYS.flatMap(d => d.prices)) * 1.02;
  const W = 760, H = 208, padL = 44, padR = 14, padT = 12, padB = 24;
  const xw = W - padL - padR, yh = H - padT - padB;
  const X = h => padL + (h / 23) * xw;
  const Y = v => padT + (1 - v / YMAX) * yh;
  const path = p => p.map((v, h) => (h ? "L" : "M") + X(h).toFixed(1) + " " + Y(v).toFixed(1)).join(" ");
  function dayCard(d) {
    const o = oraclePicks(d.prices);
    let grid = "", xlab = "";
    for (const g of [0, 50, 100, 150, 200]) {
      grid += `<line x1="${padL}" x2="${W - padR}" y1="${Y(g)}" y2="${Y(g)}" stroke="var(--grid)" stroke-width="1"/>`
            + `<text x="${padL - 8}" y="${Y(g) + 3.5}" text-anchor="end" font-size="10.5" fill="var(--muted)" font-family="var(--mono)">${g}</text>`;
    }
    for (const h of [0, 6, 12, 18, 23]) {
      xlab += `<text x="${X(h)}" y="${H - 7}" text-anchor="middle" font-size="10.5" fill="var(--muted)" font-family="var(--mono)">${hh(h)}h</text>`;
    }
    const oracleMarks = [...o.cheap, ...o.dear].map(h =>
      `<circle cx="${X(h)}" cy="${Y(d.prices[h])}" r="6.5" fill="none" stroke="var(--muted)" stroke-width="1.5"/>`).join("");
    const mark = (h, c) => `<circle cx="${X(h)}" cy="${Y(d.prices[h])}" r="5" fill="var(${c})" stroke="var(--card)" stroke-width="2"/>`;
    const lbl = (hs, txt) => {
      const h = hs[0], above = d.prices[h] < YMAX * 0.55;
      return `<text x="${X(h)}" y="${Y(d.prices[h]) + (above ? -12 : 18)}" text-anchor="middle" font-size="10.5" font-weight="600" letter-spacing=".08em" fill="var(--ink2)" font-family="var(--mono)">${txt}</text>`;
    };
    const buyAvg = avg(d.buy.map(h => d.prices[h])), sellAvg = avg(d.sell.map(h => d.prices[h]));
    return `
    <div class="day">
      <div class="day-head">
        <span class="date">${d.target}</span><span class="wd">${d.weekday}</span>
        <span class="chips">
          <span class="chip ${d.pnl >= 0 ? "pnl-pos" : "pnl-neg"}">${d.pnl >= 0 ? "+" : "−"}${fmt(Math.abs(d.pnl))} €</span>
          <span class="chip">capture ${d.capture != null ? (d.capture * 100).toFixed(1) + "%%" : "n/a"}</span>
          ${d.tau != null ? `<span class="chip">tau ${d.tau.toFixed(3)}</span>` : ""}
        </span>
      </div>
      <p class="day-sub">Bought <span class="m">${d.buy.map(hh).join("·")}h</span> at avg
        <span class="m">${fmt(buyAvg)} €/MWh</span>, sold <span class="m">${d.sell.map(hh).join("·")}h</span> at avg
        <span class="m">${fmt(sellAvg)} €/MWh</span> — hours picked from ${d.basisDate}'s profile.
        Oracle best: <span class="m">${fmt(d.oracle)} €</span>.</p>
      <div class="chart-box" data-day="${d.target}">
        <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Hourly prices for ${d.target}">
          ${grid}${xlab}
          <line x1="${padL}" x2="${W - padR}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)" stroke-width="1"/>
          <path d="${path(d.basis)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="3 4" opacity=".65"/>
          <path d="${path(d.prices)}" fill="none" stroke="var(--ink2)" stroke-width="2" stroke-linejoin="round"/>
          <line class="xh" x1="0" x2="0" y1="${padT}" y2="${H - padB}" stroke="var(--axis)" stroke-width="1" style="display:none"/>
          ${oracleMarks}${d.buy.map(h => mark(h, "--buy")).join("")}${d.sell.map(h => mark(h, "--sell")).join("")}
          ${lbl(d.buy, "BUY")}${lbl(d.sell, "SELL")}
          <circle class="hovpt" r="3.5" fill="var(--ink)" style="display:none"/>
          <rect x="${padL}" y="${padT}" width="${xw}" height="${yh}" fill="transparent"/>
        </svg>
        <div class="tip"></div>
      </div>
    </div>`;
  }
  document.getElementById("days").innerHTML = DAYS.map(dayCard).join("");
  document.getElementById("legend").innerHTML = [
    ['<svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke="var(--ink2)" stroke-width="2"/></svg>', "target-day price (€/MWh)"],
    ['<svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="3 4"/></svg>', "basis day — the decision input"],
    ['<svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--buy)"/></svg>', "committed buy hours"],
    ['<svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--sell)"/></svg>', "committed sell hours"],
    ['<svg width="14" height="14"><circle cx="7" cy="7" r="5.5" fill="none" stroke="var(--muted)" stroke-width="1.5"/></svg>', "oracle's picks (hindsight)"]
  ].map(([sw, t]) => `<span class="li">${sw}${t}</span>`).join("");
  document.querySelectorAll(".chart-box").forEach(box => {
    const d = DAYS.find(x => x.target === box.dataset.day);
    const svg = box.querySelector("svg"), tip = box.querySelector(".tip");
    const xh = svg.querySelector(".xh"), pt = svg.querySelector(".hovpt");
    svg.addEventListener("mousemove", e => {
      const r = svg.getBoundingClientRect();
      const mx = (e.clientX - r.left) * (W / r.width);
      const h = Math.max(0, Math.min(23, Math.round((mx - padL) / xw * 23)));
      xh.setAttribute("x1", X(h)); xh.setAttribute("x2", X(h)); xh.style.display = "";
      pt.setAttribute("cx", X(h)); pt.setAttribute("cy", Y(d.prices[h])); pt.style.display = "";
      const role = d.buy.includes(h) ? " · BUY" : d.sell.includes(h) ? " · SELL" : "";
      tip.innerHTML = `${hh(h)}:00${role}<br><span class="t2">day&nbsp;</span>${fmt(d.prices[h])} €/MWh` +
                      `<br><span class="t2">basis</span> ${fmt(d.basis[h])} €/MWh`;
      tip.style.display = "block";
      const bx = (X(h) / W) * r.width;
      tip.style.left = Math.min(r.width - 150, Math.max(4, bx + 12)) + "px";
      tip.style.top = "10px";
    });
    svg.addEventListener("mouseleave", () => {
      tip.style.display = "none"; xh.style.display = "none"; pt.style.display = "none";
    });
  });
</script>
"""


def main() -> None:
    args = [a for a in sys.argv[1:]]
    slug = "es"
    if "--market" in args:
        i = args.index("--market")
        slug = args[i + 1]
        del args[i:i + 2]
    out = Path(args[0]) if args else ROOT / ("site/index.html" if slug == "es"
                                             else f"site/{slug}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    html = "<!doctype html><html><head><meta charset=\"utf-8\">" \
           "<meta name=\"viewport\" content=\"width=device-width," \
           "initial-scale=1\"></head><body>" + build(slug) + "</body></html>"
    out.write_text(html)
    print(f"rendered {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
