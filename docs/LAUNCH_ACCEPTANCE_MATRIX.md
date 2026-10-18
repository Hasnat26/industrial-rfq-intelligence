# Launch Acceptance Matrix

Launch gates tracked independently from implementation work. A task can be
implemented (repository evidence) while its live acceptance test remains
unverified. Both facts are shown separately. Updated 2026-10-12 after PR #129 exception-boundary hardening; repository evidence and hosted acceptance remain separate.

Legend: PASS = verified with linked evidence. NOT VERIFIED = no execution
evidence. BLOCKED = owner action required. PARTIAL = partially verified.

## Controlled-pilot gates

| # | Gate | Implementation | Live/acceptance evidence | Result |
|---|------|----------------|--------------------------|--------|
| G1 | Main CI green on release commit | CI workflow complete | Run #624 (`38237349041`) passed all jobs on main SHA `fe44588116f6d1afb0a7c70a0a3b661ec3db6593` | PASS |
| G2 | Deployed commit verified separately from code | Render auto-deploy | Deployment `dep-db5s11tckfvc73b8ief0` = `2a31c00`; PR #122 adds runtime extraction hardening in `src/freellmpool/industrial.py`; latest confirmed deployment remains `2a31c00`, so deploy state must be checked separately | PASS |
| G3 | Migration chain valid | Alembic chain + `p9meta001` index alignment | `postgres-migrations` CI job green (clean PostgreSQL 16, `upgrade head` + `check`) | PASS |
| G4 | Live schema baseline established | N/A (live-state gate) | Requires owner laptop + allowlisted connection; no live `alembic_version` verified | BLOCKED (P1-DB-01) |
| G5 | Durable database secured before 2026-11-08 | N/A (provisioning gate) | Render Free instance expiry recorded; current provider state needs dashboard check | BLOCKED (P1-DB-04) |
| G6 | Live backup created from real Render DB | Backup tooling merged (#106/#114/#115/#117) | No archive produced from the live database yet | NOT VERIFIED (P2-BK-03) |
| G7 | Restore drill into isolated target | Tooling + verification checks merged | Scratch drills passed; no live-derived restore drill yet | NOT VERIFIED (P2-BK-04) |
| G8 | Backup tooling usable on owner's laptop | Explicit PostgreSQL tool paths; independent drill connection; live source/target identity guard | PR #117 merged; Run #598 passed; scratch drill details in runbook | PASS (repository + scratch only) |
| G9 | Hosted readiness | `/health` + database-backed `/ready` | External HTTP probes 2026-10-12: `/health` 200, `/ready` 200 `database:ok` | PASS |
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
| G21 | Logging/secrets/error handling (repository-level) | Rejected provider URLs are not logged verbatim; reconciliation errors use a generic client response and failure-record persistence is best effort | PR #129 code/test commit `179257b9777285b11f1ede73b27beef0df710793`; Run #648 passed all five jobs. No hosted log review or live failure injection was performed | PASS (repository tests); hosted NOT VERIFIED |

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
