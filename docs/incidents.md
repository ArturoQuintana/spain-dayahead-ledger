# Incident log (escape-rate ledger)

One line per incident: what fired, WHO NOTICED FIRST (machinery | human |
agent-session — the last two count as ESCAPES under the closed defect loop),
resolution, detector added. Reviewed at month-ends. Seeded retroactively
2026-08-21 from the full project history.

| Date | Incident | Noticed first by | Resolution | Detector added |
|---|---|---|---|---|
| 2026-07-31 | Tick ran without writing launchd log (route unknown) | agent-session (ESCAPE) | benign; did not recur | none (class retired with launchd) |
| 2026-08-04 | DNS outage at tick; no fetch; primary receipt for 08-05 lost | machinery (heartbeat FAIL) + agent-session same day | recovery tick; honest miss | fetch retries +5m/+15m + tests |
| 2026-08-05..06 | Machine moved Madrid→Tampa; local-time schedule silently wrong; 08-07 receipt lost | agent-session (ESCAPE) | server migration; Madrid-keyed market_today() | market_today test; server is sole writer |
| 2026-08-10 | GitHub silently stopped accepting the Mac's SSH key; morning push failed | agent-session (ESCAPE) | Mac remote moved to HTTPS/gh | none — class mitigated by demoting Mac; gh-token expiry queued in continuity note |
| 2026-08-19..20 | Server SSH lockout by co-tenant hardening; ALERT_* secrets undeliverable; ~1 week without inbox digests | human (ESCAPE) | new esios-vps identity; least-privilege access | INFRA.md contract queued; dedicated-server triggers defined |
| 2026-08-20 | Hetzner egress block on SMTP 465; first server email send timed out | agent-session at live test (ESCAPE) | switch to 587+STARTTLS | port checked in code path; tests updated |
| 2026-08-20 | Artifact publish version conflict | machinery (409) | resynced baseline | n/a (artifact deprecated for Pages) |
| 2026-08-21 | OTS manifests silently rewritten by same-day re-ticks; 12/13 proofs invalidated (live defect in ots_stamp) | machinery (independent auditor) | stamped originals restored from git history; stamp logic made immutable-per-slot | regression test test_ots_stamped_manifest_is_immutable* |
| 2026-08-23 | ERCOT go-live: ercot.com 403s the Helsinki server (US-geo/datacenter block, whole domain); fetch-retry backoff also stalled the tick ~20min | machinery (live server seed run) | ERCOT de-scheduled from server_tick; DE unaffected; source alternatives under review | de-scheduled; per-market source reachability now checked at wire-time |

Escape rate: **5 of 9 incidents were escapes** (the 2026-08-21 OTS finding was caught by the Monday-auditor machinery — the closed loop's first win) (noticed
by a human or by an agent happening to look, not by machinery). This number
is the justification for the closed-defect-loop apparatus — and the number
the next 60 rolling days must drive to zero for the core to be declared
reliable.

Review findings (leak-guard clock hole, torn-write risk, etc.) are tracked
in docs/BACKLOG.md, not here — this file is for things that FIRED.
