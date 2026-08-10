"""CLI: `python -m esios_paper tick` (the daily pass) / `status` (ledger summary)."""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import urllib.request
from pathlib import Path

from .loop import DATA_DIR, LEDGER, RECEIPTS, _load_jsonl, tick

REPO = Path(__file__).resolve().parents[2]
OTS_DIR = DATA_DIR / "ots"


def _env(key: str) -> str | None:
    """Environment first, then the repo's .env (KEY=VALUE lines, gitignored)."""
    if key in os.environ:
        return os.environ[key]
    envf = REPO / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def heartbeat(ok: bool, *, _urlopen=urllib.request.urlopen) -> None:
    """Ping the external healthcheck: success iff TODAY'S RECEIPT EXISTS (the
    one thing the loop must produce daily); /fail when the tick ran but could
    not commit (late wake, incomplete basis) so the alert is immediate rather
    than after grace. No URL configured -> silently off. Never fatal."""
    url = _env("ESIOS_HEARTBEAT_URL")
    if not url:
        return
    try:
        _urlopen(url if ok else url.rstrip("/") + "/fail", timeout=10)
        print(f"[esios-paper] heartbeat pinged{'' if ok else ' (FAIL signal)'}")
    except Exception as exc:
        print(f"[esios-paper] heartbeat ping failed: {exc}")


def ots_manifest(label: str) -> str:
    """Text manifest binding the audit trail's current state: sha256 of the
    receipts and ledger files. Stamping this (OpenTimestamps) proves the
    receipts existed BEFORE the auction published — trustlessly, unlike git
    host timestamps. Pure text builder, unit-tested."""
    lines = [f"esios-paper audit manifest {label}"]
    for path in (RECEIPTS, LEDGER):
        digest = (hashlib.sha256(path.read_bytes()).hexdigest()
                  if path.exists() else "absent")
        lines.append(f"sha256({path.name})={digest}")
    return "\n".join(lines) + "\n"


def ots_stamp(label: str, *, _run=subprocess.run) -> None:
    """Write Data/ots/<label>.txt and stamp it via the canonical OTS client
    (through uvx, so the project itself stays stdlib-only). The .txt + .ots
    proof ride the same git backup as the data they attest. Best effort by
    design: a calendar/network failure must never fail the tick."""
    try:
        OTS_DIR.mkdir(parents=True, exist_ok=True)
        manifest = OTS_DIR / f"{label}.txt"
        manifest.write_text(ots_manifest(label))
        proof = manifest.with_suffix(".txt.ots")
        if proof.exists():          # idempotent: second pass same day
            print("[esios-paper] ots: proof already exists")
            return
        r = _run(["uvx", "--from", "opentimestamps-client", "ots",
                  "stamp", str(manifest)],
                 capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and proof.exists():
            print(f"[esios-paper] ots: stamped {manifest.name}")
        else:
            print(f"[esios-paper] ots: STAMP-FAILED "
                  f"{(r.stderr or r.stdout).strip()[:200]}")
    except Exception as exc:
        print(f"[esios-paper] ots: STAMP-FAILED {exc}")


def git_backup(label: str) -> None:
    """Commit + push Data/ (prices, receipts, ledger — the audit trail). Best
    effort by design: a failed commit/push must never fail the tick (the next
    day's push carries today's commit), but the outcome is always logged."""
    def run(*args: str):
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True)
    run("add", "Data")
    if run("diff", "--cached", "--quiet").returncode == 0:
        print("[esios-paper] backup: up to date")
        return
    c = run("commit", "-m", f"data: tick {label}")
    if c.returncode != 0:
        print(f"[esios-paper] backup: COMMIT-FAILED {c.stderr.strip()[:200]}")
        return
    p = run("push")
    print("[esios-paper] backup: pushed" if p.returncode == 0
          else f"[esios-paper] backup: committed, PUSH-FAILED (will ride next "
               f"push) {p.stderr.strip()[:200]}")


def cmd_tick() -> int:
    s = tick()
    if s.get("fetch_error"):
        print(f"[esios-paper] FETCH-ERROR {s['fetch_error']}")
    for e in s["settled"]:
        print(f"[esios-paper] SETTLED {e['target']} [{e['strategy']} "
              f"v{e['strategy_version']}]: pnl={e['pnl_eur']:+.2f} EUR "
              f"(oracle {e['oracle_pnl_eur']:+.2f}, capture {e['capture']}, "
              f"tau {e.get('tau')})")
    for r in s["committed"]:
        print(f"[esios-paper] COMMITTED {r['target']} [{r['strategy']} "
              f"v{r['strategy_version']}]: buy {r['buy_hours']} "
              f"sell {r['sell_hours']} (basis {r['basis_day']})")
    for msg in s["skipped"]:
        print(f"[esios-paper] SKIPPED commit: {msg}")
    ots_stamp(s["date"])
    git_backup(s["date"])
    heartbeat(s["primary_receipt_stands"])
    print(f"[esios-paper] tick done {json.dumps({k: v if isinstance(v, (str, bool)) else bool(v) for k, v in s.items()})}")
    return 0


def cmd_status() -> int:
    alerts = DATA_DIR / "CROSSCHECK-ALERTS.log"
    if alerts.exists():
        print("!! CROSSCHECK ALERTS present — the two price routes disagreed; "
              "investigate before trusting recent settlements "
              f"({alerts.name}, {len(alerts.read_text().splitlines())} entries)")
    ledger = _load_jsonl(LEDGER)
    receipts = _load_jsonl(RECEIPTS)
    settled_keys = {(e["target"], e["strategy"], e["strategy_version"]) for e in ledger}
    open_receipts = [r for r in receipts
                     if (r["target"], r["strategy"], r["strategy_version"])
                     not in settled_keys]
    print(f"receipts: {len(receipts)} total, {len(open_receipts)} open")
    if not ledger:
        print("ledger: empty (no settled days yet)")
        return 0
    by_strategy: dict[tuple[str, str], list[dict]] = {}
    for e in ledger:
        by_strategy.setdefault((e["strategy"], e["strategy_version"]), []).append(e)
    for (strat, ver), es in sorted(by_strategy.items()):
        pnl = [e["pnl_eur"] for e in es]
        caps = [e["capture"] for e in es if e.get("capture") is not None]
        cap_s = f"{statistics.fmean(caps) * 100:.0f}%" if caps else "n/a"
        print(f"  {strat} v{ver}: {len(pnl)} settled | total {sum(pnl):+.2f} EUR | "
              f"mean {statistics.fmean(pnl):+.2f}/day | "
              f"win rate {sum(p > 0 for p in pnl) / len(pnl) * 100:.0f}% | "
              f"mean capture {cap_s}")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    if cmd == "tick":
        return cmd_tick()
    if cmd == "status":
        return cmd_status()
    print(f"unknown command {cmd!r}; use: tick | status")
    return 2


if __name__ == "__main__":
    sys.exit(main())
