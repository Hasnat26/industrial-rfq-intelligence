# Launch Acceptance Matrix

Launch gates tracked independently from implementation work. A task can be
implemented (repository evidence) while its live acceptance test remains
unverified. Both facts are shown separately. Updated 2026-10-13 after T24-R22 verified Render deployment recovery; repository evidence and hosted acceptance remain separate.

Legend: PASS = verified with linked evidence. NOT VERIFIED = no execution
evidence. BLOCKED = owner action required. PARTIAL = partially verified.

## Controlled-pilot gates

| # | Gate | Implementation | Live/acceptance evidence | Result |
|---|------|----------------|--------------------------|--------|
| G1 | Main CI green on release commit | CI workflow complete | Run #653 (`38288890112`) passed all five jobs on main SHA `f363adc562a494de57cca58c530c99afdfba2818` — <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38288890112> | PASS |
| G2 | Deployed commit verified separately from code | Render deployment record and event history | Deployment `dep-db6j008n74is73a7thkg` is `live` on exact SHA `f363adc562a494de57cca58c530c99afdfba2818`; `build_ended=succeeded`; `deploy_ended=succeeded` at `2026-10-12T19:09:08.269869Z`. Previous deployment `dep-db5s11tckfvc73b8ief0` (`2a31c006a6e7e3174c6375c6f5226cb3430f373c`) is `deactivated`. | PASS |
| G3 | Migration chain valid | Alembic chain + `p9meta001` index alignment | `postgres-migrations` CI job green (clean PostgreSQL 16, `upgrade head` + `check`) | PASS |
| G4 | Live schema baseline established | N/A (live-state gate) | Requires owner laptop + allowlisted connection; no live `alembic_version` verified | BLOCKED (P1-DB-01) |
| G5 | Durable database secured before 2026-11-08 | N/A (provisioning gate) | Render Free instance expiry recorded; current provider state needs dashboard check | BLOCKED (P1-DB-04) |
| G6 | Live backup created from real Render DB | Backup tooling merged (#106/#114/#115/#117) | No archive produced from the live database yet | NOT VERIFIED (P2-BK-03) |
| G7 | Restore drill into isolated target | Tooling + verification checks merged | Scratch drills passed; no live-derived restore drill yet | NOT VERIFIED (P2-BK-04) |
| G8 | Backup tooling usable on owner's laptop | Explicit PostgreSQL tool paths; independent drill connection; live source/target identity guard | PR #117 merged; Run #598 passed; scratch drill details in runbook | PASS (repository + scratch only) |
| G9 | Hosted readiness | Render runtime startup + `/ready` | Deployment `dep-db6j008n74is73a7thkg` startup completed at `2026-10-12T19:08:56.755388973Z`; Render readiness request `GET /ready` returned HTTP 200 at `2026-10-12T19:09:06.869985364Z`. This is deployment/readiness evidence, not security acceptance. | PASS (deployment readiness only) |
| G10 | Authenticated smoke flow (hosted) | Auth + full API implemented | No recorded hosted run with test accounts | NOT VERIFIED (P4-AUTH-02) |
| G11 | Tenant isolation (automated) | Tenant guards in every repository-scoped query | 22 tests in `tests/test_auth_tenant.py` incl. cross-tenant read/mutation sweeps and the completed offer-scoped IDOR sweep (P4-AUTH-03) | PASS |
| G12 | Tenant isolation (hosted) | Same code path | Not executed against the deployment | NOT VERIFIED (P4-AUTH-02) |
| G13 | Entitlement enforcement | Server-side metered-write checks | `tests/test_commercial.py` automated | PASS |
| G14 | Production fail-closed configuration | Rejects SQLite/auto-create/weak secrets | `tests/test_release_config.py` automated | PASS |
| G15 | Security scanning | Bandit/pip-audit/zizmor in CI; exceptions file validated | Every CI run; standalone Security + CodeQL workflows disabled (`disabled_fork`) | PARTIAL (P0-CI-02) |
| G16 | Prompt-injection resistance for RFQ docs | Explicit untrusted-data delimiters, instruction hierarchy, input/output caps | PR #122 CI Run #611 passed synthetic adversarial/size-limit regression tests; hosted attack test not run | PASS (repository tests); hosted NOT VERIFIED |
| G17 | Core RFQ workflow (intake→export) | Implemented | Broad automated coverage; hosted run not recorded | PARTIAL |
| G18 | Pilot onboarding package | Partial docs and sample artifacts exist | `examples/industrial_rfq/sample_input.json` and `sample_report.md` are already on main; customer-facing quickstart, complete quotation/source package, and known-limitations one-pager remain pending. PRs #128, #130, and #131 are open/unmerged and are not counted as delivered/deployed | PARTIAL (P7-OPS-02) |
| G19 | Incident & support procedure | Feedback triage classified | Contact procedure needs owner input | PARTIAL (P7-OPS-03) |
| G20 | Backup/restore runbook matches tooling | `docs/DB_BACKUP_RUNBOOK.md` | PR #117 runbook matches script parameters; Run #598 passed | PASS (documentation/code consistency; live recovery still unverified) |
| G21 | Logging/secrets/error handling (repository-level) | Rejected provider URLs are not logged verbatim; reconciliation errors use a generic client response and failure-record persistence is best effort | PR #129 merged as `f363adc562a494de57cca58c530c99afdfba2818`; main CI Run #653 passed all five jobs. Deployment `dep-db6j008n74is73a7thkg` is live on this SHA. No hosted log review or live failure injection was performed. | PASS (repository tests); hosted NOT VERIFIED |

| G22 | Hosted security acceptance (overall) | Repository-level security changes are merged and CI-verified | Deployment recovery is verified, but no separate authorized hosted security acceptance checks were executed for this task. Hosted authenticated tenant isolation, hosted logging/error behavior, live migration baseline, and backup/restore remain separate gates. | NOT VERIFIED |

## Commercial-production gates (additional)

| # | Gate | Result | Notes |
|---|------|--------|-------|
| C1 | Payment provider configured and webhooks verified | BLOCKED | Owner approval + provider account required (P6-BILL-02) |
| C2 | Idempotency/replay of billing lifecycle tested live | BLOCKED | Depends on C1 |
| C3 | Monitoring/alerting external to platform | BLOCKED | Owner tooling decision (P7-OPS-04) |
| C4 | Rate limiting suitable for topology | PASS (for the single-replica topology) | In-process failure limiter on auth endpoints; general write-path policy + single-replica limitation documented in `docs/SAAS_AUTH_AND_TENANCY.md` (P5-SEC-02, decision-log pass 2026-10-15); multi-replica scale-up requires an edge/shared-store limiter |
| C5 | Original-document retention decision | LIMITATION | Only extracted text/pages retained; add object storage before claiming retention |
| C6 | One completed pilot feedback cycle | NOT VERIFIED | Per `docs/PILOT_LAUNCH.md` section 10 |

## Decision rule

Passing CI alone is never sufficient for G4–G8, G10, G12, or any commercial
gate. Each NOT VERIFIED gate must be executed against the live system (or the
real database) with recorded evidence before it can change state.
