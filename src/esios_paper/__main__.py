"""CLI: `python -m esios_paper tick` (the daily pass) / `status` (ledger summary)."""
from __future__ import annotations

import hashlib
import json
import os
import smtplib
import statistics
import subprocess
import sys
import urllib.request
from email.message import EmailMessage
from math import comb
from pathlib import Path

from .loop import DATA_DIR, LEDGER, RECEIPTS, STRATEGY, _load_jsonl, tick

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


def _sign_p(wins: int, n: int) -> float:
    """One-sided binomial P(X >= wins | n, 0.5) — the pre-registered test."""
    return sum(comb(n, i) for i in range(wins, n + 1)) / 2 ** n


def build_digest() -> tuple[str, str] | None:
    """(subject, body) for the daily inbox digest — same numbers and house
    rules as the cloud routine: lead with the outcome, never soften the math,
    no superiority claims below the pre-registered bar."""
    ledger = _load_jsonl(LEDGER)
    if not ledger:
        return None
    latest = max(e["target"] for e in ledger)
    today = {e["strategy"]: e for e in ledger if e["target"] == latest}
    prim = [e for e in ledger if e["strategy"] == STRATEGY]
    total = sum(e["pnl_eur"] for e in prim)
    caps = [e["capture"] for e in prim if e.get("capture") is not None]
    wins = sum(1 for e in prim if e["pnl_eur"] > 0)
    losing_today = any(e["pnl_eur"] < 0 for e in today.values())
    crosscheck = (DATA_DIR / "CROSSCHECK-ALERTS.log").exists()

    lines = [f"Settlement {latest}:"]
    for name, e in sorted(today.items()):
        cap = f"{e['capture'] * 100:.1f}%" if e.get("capture") is not None else "n/a"
        tau = f", tau {e['tau']:.3f}" if e.get("tau") is not None else ""
        lines.append(f"  {name}: {e['pnl_eur']:+.2f} EUR ({cap}{tau})")
    lines.append("")
    lines.append(
        f"Primary: {total:+.2f} EUR over {len(prim)} days | "
        f"win rate {wins}/{len(prim)} | mean capture "
        f"{statistics.fmean(caps) * 100:.1f}% | gate {min(len(prim), 21)}/21")

    by_day: dict[str, dict[str, float]] = {}
    for e in ledger:
        by_day.setdefault(e["target"], {})[e["strategy"]] = e["pnl_eur"]
    for shadow in sorted({e["strategy"] for e in ledger} - {STRATEGY}):
        deltas = [v[shadow] - v[STRATEGY] for v in by_day.values()
                  if shadow in v and STRATEGY in v]
        w = sum(1 for d in deltas if d > 0.01)
        l = sum(1 for d in deltas if d < -0.01)
        n = w + l
        p = _sign_p(w, n) if n else 1.0
        lines.append(
            f"{shadow} vs primary: {sum(deltas):+.2f} EUR over {len(deltas)} "
            f"shared ({w}W-{len(deltas) - w - l}T-{l}L, sign p={p:.3f}"
            f"{', bar not met' if not (n >= 30 and p < 0.05) else ', BAR MET'})")

    prime = today.get(STRATEGY)
    if prime is not None and prime.get("tb2_spread") is not None:
        week = [e for e in prim if e.get("tb2_spread") is not None][-7:]
        lines.append(
            f"Regime: neg_hours {prime.get('neg_hours')} | tb2 "
            f"{prime['tb2_spread']:.0f} EUR (7d mean "
            f"{statistics.fmean(e['tb2_spread'] for e in week):.0f})")

    alerts = []
    if losing_today:
        alerts.append("losing day in latest settlement (data, not a bug)")
    if crosscheck:
        alerts.append("CROSSCHECK-ALERTS.log present — price routes disagreed")
    if alerts:
        lines.insert(0, "ALERTS: " + "; ".join(alerts))
        lines.insert(1, "")
    subject = (("ALERT — " if alerts else "") +
               f"esios digest {latest} · "
               f"{(prime or {}).get('pnl_eur', 0):+.0f} € · {wins}/{len(prim)}")
    lines.append("")
    lines.append("Paper money, upper bound (exchange fees only). "
                 "Full ledger: arturoquintana.github.io/spain-dayahead-ledger")
    return subject, "\n".join(lines)


def email_digest(summary: dict, *, _smtp=smtplib.SMTP) -> None:
    """Send the digest after ticks that settled something, or on trouble
    (fetch failure / primary receipt missing). Config in .env: ALERT_EMAIL_TO
    + ALERT_SMTP_PASSWORD (Gmail app password; ALERT_SMTP_USER defaults to
    the recipient). Port 587 + STARTTLS deliberately: Hetzner blocks
    outbound 465/25 by default. No config -> silently off. Never fatal — a
    MISSING daily email is itself a dead-man signal, like the heartbeat."""
    to = _env("ALERT_EMAIL_TO")
    password = _env("ALERT_SMTP_PASSWORD")
    if not to or not password:
        return
    trouble = bool(summary.get("fetch_error")) or \
        not summary.get("primary_receipt_stands", True)
    if not summary.get("settled") and not trouble:
        return                      # commit-only passes stay silent
    try:
        built = build_digest()
        if built is None:
            return
        subject, body = built
        if trouble:
            problems = []
            if summary.get("fetch_error"):
                problems.append(f"fetch_error: {summary['fetch_error']}")
            if not summary.get("primary_receipt_stands", True):
                problems.append("PRIMARY RECEIPT DOES NOT STAND for tomorrow")
            body = "TICK TROUBLE: " + "; ".join(problems) + "\n\n" + body
            if not subject.startswith("ALERT"):
                subject = "ALERT — " + subject
        msg = EmailMessage()
        msg["From"] = _env("ALERT_SMTP_USER") or to
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with _smtp("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(_env("ALERT_SMTP_USER") or to, password)
            s.send_message(msg)
        print(f"[esios-paper] digest emailed ({subject!r})")
    except Exception as exc:
        print(f"[esios-paper] digest email FAILED (non-fatal): {exc}")


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
        content = ots_manifest(label)
        # A STAMPED MANIFEST IS IMMUTABLE. The pre-2026-08-21 version
        # rewrote <date>.txt on every pass and skipped stamping when a proof
        # existed — so the second tick of a day (post-settlement hashes)
        # silently invalidated the morning's proof (audit finding, incident
        # 2026-08-21). Now: if the audit trail moved after a stamp, the new
        # state gets a NEW suffixed manifest; stamped pairs are never touched.
        for n in range(1, 25):
            manifest = OTS_DIR / (f"{label}.txt" if n == 1
                                  else f"{label}-{n}.txt")
            proof = manifest.with_suffix(".txt.ots")
            if proof.exists():
                if manifest.read_text() == content:
                    print(f"[esios-paper] ots: {manifest.name} already "
                          "attested for current state")
                    return
                continue            # stamped for an older state; next slot
            manifest.write_text(content)
            r = _run(["uvx", "--from", "opentimestamps-client", "ots",
                      "stamp", str(manifest)],
                     capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and proof.exists():
                print(f"[esios-paper] ots: stamped {manifest.name}")
            else:
                print(f"[esios-paper] ots: STAMP-FAILED "
                      f"{(r.stderr or r.stdout).strip()[:200]}")
            return
        print("[esios-paper] ots: STAMP-FAILED (slot overflow)")
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
    email_digest(s)
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
