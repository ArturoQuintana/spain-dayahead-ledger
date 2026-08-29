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
| 2026-08-28 | FR (private, derived-only ENTSO-E) day-ahead prices reached the PUBLIC ES mirror: publish_mirror.sh's HARDCODED exclude list (de/ercot/it/pt) was not updated when FR was added, so Data/fr/prices.json + ots were committed and pushed to github.com/ArturoQuintana/spain-dayahead-ledger from FR go-live (~10:30 UTC) until caught ~16:10 UTC. No harm to the record; a redistribution-policy violation for low-sensitivity, widely-available data. Root cause = the deferred Phase-3 drift (publish_mirror not registry-derived) + my omission when building FR. | agent-session (ESCAPE), noticed while republishing the mirror during the ES data migration | publish_mirror ES excludes made REGISTRY-DERIVED (`for s in $(… markets)`, exclude unless es) + `--delete-excluded` to purge; FR removed from the mirror and pushed | test_mirror_is_deny_by_default_allowlist (fails if any per-market exclude is hardcoded) |
| 2026-08-29 | The one-project consolidation migrated DE's history into the PUBLIC `talea` repo as a single bulk commit (fd4bdd49, 2026-08-29), so talea's DE git-history begins with a multi-day sync — the timing "weak check" (committed_at vs the commit that introduced a receipt) no longer corroborates pre-08-29 DE dates from talea alone. VERIFY.md still claimed DE "git-attested (every tick commits and pushes)" and disclosed no DE evidence boundary, though ES's equivalent pre-08-10 bulk-import boundary IS disclosed. (Also: ARCHITECTURE's Automation section still described per-mirror verify workflows.) No arithmetic/money error; per-tick DE evidence still exists in the private repo + the frozen germany-dayahead-ledger mirror. The agent's own "are all docs updated?" sweep this session MISSED both. | machinery (independent auditor — first talea run) | VERIFY.md gains a DE evidence-boundary disclosure parallel to ES's (per-tick history in the private repo / frozen germany-dayahead-ledger mirror; use OTS 08-27+); ARCHITECTURE Automation corrected to one talea repo / one verify.yml --all | test_verify_discloses_migrated_market_evidence_boundaries |
| 2026-08-24 | The 2026-08-21 restoration was correct-but-incomplete: for 13 dates (2026-08-09 through 2026-08-21) the OTS-stamped `<date>.txt` anchors the FIRST daily tick's state, not that day's final settlement — the `<date>-2.txt` slot created during restoration holds the true final state but was never itself submitted to OpenTimestamps, so those 13 dates currently have no Bitcoin anchor of their final content. VERIFY.md's "every proof now matches" was an overclaim. No data is wrong (arithmetic re-verifies exactly); only the proof coverage is incomplete pre-2026-08-22, when ots_stamp began covering every slot on every tick. | machinery (independent auditor) | VERIFY.md corrected to state the actual coverage; whether to mint new proofs anchoring the current final state for those 13 dates is an evidentiary-claims decision left to the user | scripts/audit_ots_manifests.py + regression test (flags any written manifest slot with no matching .ots) |

Escape rate: **6 of 11 incidents were escapes** (the 2026-08-21 OTS finding was caught by the Monday-auditor machinery — the closed loop's first win; the 2026-08-28 FR mirror leak was an escape — machinery did not flag it, an agent-session did) (noticed
by a human or by an agent happening to look, not by machinery). This number
is the justification for the closed-defect-loop apparatus — and the number
the next 60 rolling days must drive to zero for the core to be declared
reliable.

Review findings (leak-guard clock hole, torn-write risk, etc.) are tracked
in the project's internal backlog (not part of this public mirror), not
here — this file is for things that FIRED.
