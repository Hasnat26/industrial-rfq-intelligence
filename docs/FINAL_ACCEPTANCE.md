# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the repository and hosted service. It distinguishes repository CI, deployed runtime, and production operational readiness.

| Gate | Evidence status | Result |
|---|---|---|
| CI validation for current main | Main CI Run #653 (`38288890112`) passed all five jobs on current main tip `f363adc562a494de57cca58c530c99afdfba2818` (the previously recorded Run #612 `38219830664` on `656781d2f4761d4a77a43ee93be74d671f6a0b61` is superseded) | PASS |
| CI validation for deployed runtime commit | Main CI Run #653 (`38288890112`) completed successfully for the deployed commit `f363adc562a494de57cca58c530c99afdfba2818`; the same pipeline shape is green on every main commit since the Run #582 era | PASS |
| Latest deployed source commit | Render deployment `dep-db6j008n74is73a7thkg` for commit `f363adc562a494de57cca58c530c99afdfba2818` reached `live` (deploy event `evt-db6j0l48q0ns73e9gq5g` succeeded 2026-10-12T19:09:08Z); the previous deployment `dep-db5s11tckfvc73b8ief0` for `2a31c006a6e7e3174c6375c6f5226cb3430f373c` is now `deactivated` | DEPLOYED |
| Runtime-code delta | The current live Render deployment `dep-db6j008n74is73a7thkg` targets `f363adc562a494de57cca58c530c99afdfba2818`, which is the current main tip, so there is no undeployed runtime-code delta between main and the deployed commit | NO RUNTIME DELTA |
| Hosted startup/readiness | Render logs for the current live deployment `dep-db6j008n74is73a7thkg` show application startup complete (2026-10-12T19:08:56Z) and `GET /ready` returning `200 OK` (2026-10-12T19:09:06Z); an independent external HTTP probe on 2026-10-12 returned `/health` 200 and `/ready` 200 `{"status":"ready","database":"ok"}` | PASS (platform log + external probe) |
| Migration schema coverage | Clean PostgreSQL 16 migration chain, `alembic current`, and `alembic check` pass in CI; live Render DB still has no `alembic_version` and has not been safely baselined or migrated | CI PASS / LIVE PENDING |
| Commercial entitlement enforcement | Package, offer, quotation batch, revision/resubmission, and document creation paths enforce plan limits and persist usage atomically | PASS (automated tests) |
| Commercial usage integrity | Manual usage writes are OWNER-only and PostgreSQL entitlement checks serialize on the organization subscription row | PASS (automated tests) |
| Security gate | Security commands and regression tests are part of the main CI gate; main CI Run #653 passed. **Hosted security acceptance remains NOT VERIFIED**; no hosted security/tenant-isolation checks were run for T24-R22. | PASS (CI); hosted NOT VERIFIED |
| Package/CLI smoke | Main CI includes wheel/sdist build and installation smoke | PASS |
| SaaS readiness surface | Dedicated FastAPI container, readiness endpoint, deployment instructions, local compose smoke surface, OCR runtime, and container CI smoke are present | PASS |
| Original binary document retention | Original uploads are intentionally not retained; only extracted text/pages are persisted | LIMITATION |
| Production payment execution | Provider-neutral billing boundary exists; provider credentials/execution are still required | EXTERNAL DEPENDENCY |
| Production fail-closed configuration | Production rejects SQLite, table auto-creation, and missing/weak billing/reconciliation secrets | PASS (automated tests) |
| Production PostgreSQL runtime | PostgreSQL DBAPI driver is packaged with the SaaS runtime dependencies | PASS |
| Production database/recovery | Current Render PostgreSQL is a Free staging database that expires on 2026-11-08 and has no managed backup; durable managed PostgreSQL and tested backup/recovery are still required | NOT YET GREEN |
| Hosted authenticated workflow | No verified authenticated end-to-end workflow and cross-tenant isolation run against the hosted deployment is recorded | PENDING |
| Hosted production validation | Live migration state, backups/restore, provider billing, production secrets/configuration, and authenticated tenant-isolation smoke remain unverified | NOT YET GREEN |

## Acceptance rule

Repository configuration alone is not execution evidence. A release claim is CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. Main CI Run #653 (`38288890112`) is confirmed successful for commit `f363adc562a494de57cca58c530c99afdfba2818`. The Render deployment `dep-db6j008n74is73a7thkg` for that same commit is live, platform logs show readiness returning `200 OK`, and an external HTTP probe on 2026-10-12 confirmed `/health` 200 and `/ready` 200. This is **Main Green and deployed**, not proof of hosted production readiness.

The authoritative remaining-work backlog is `docs/MARKET_LAUNCH_MASTER_PLAN.md`; gate-by-gate live acceptance status is tracked in `docs/LAUNCH_ACCEPTANCE_MATRIX.md`; the resume checkpoint for engineer handover is `docs/PROJECT_CONTINUITY.md`; material decisions are recorded in `docs/ENGINEERING_DECISION_LOG.md`.

The Render platform health-check path is `/ready`. This verification has platform-log evidence for successful readiness responses; it does not claim an independent external HTTP probe. The active environment configuration could not be safely confirmed from the available read-back. Do not switch the service to production mode until the database, migration, secrets, and recovery gates are ready.

## Explicit hosted acceptance boundary

**Hosted security acceptance: NOT VERIFIED.** The deployment status and readiness logs do not establish production security acceptance, authenticated tenant isolation, hosted logging/error behavior, live database migration/baseline acceptance, or backup/recovery acceptance. Those gates require separate authorized execution and evidence.

## Remaining production acceptance work

1. Provision durable managed PostgreSQL with restricted access, backups, and a tested restore procedure. The current Free staging database expires on 2026-11-08 and has no managed backups. Do not provision paid infrastructure without owner approval.
2. Audit and compare the live database schema with a clean restored backup. The live database is IP-allowlisted, so the hosted Render query connector cannot connect. Do not widen database access to the public internet just to enable the connector.
3. Establish the correct Alembic baseline only after schema equivalence is verified; then apply and verify migrations with automatic table creation disabled in production. Do not stamp or migrate the live database before this audit and an approved change window.
4. Confirm production mode, database URL, and strong billing-webhook/reconciliation secrets through protected environment configuration without exposing secret values.
5. Configure an actual billing provider and verify webhook signatures, idempotency, subscription lifecycle, and reconciliation before enabling paid plans.
6. Execute authenticated end-to-end smoke tests, including organization/tenant isolation and entitlement enforcement, against the hosted deployment.
7. Verify TLS/ingress, monitoring/alerts, rate limiting/shared state as needed, and backup/restore evidence.
8. Record the exact deployed commit, migration head, readiness result, authenticated smoke-test results, and recovery evidence.

## Portfolio-safe statement

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI Run #653 (`38288890112`) is confirmed successful for commit `f363adc562a494de57cca58c530c99afdfba2818`; Render deployment `dep-db6j008n74is73a7thkg` for the same commit reached `live`, with startup/readiness `200 OK` log evidence and a successful external probe on 2026-10-12. Hosted production remains unverified until durable database/recovery, production migration/configuration, billing-provider validation, and authenticated tenant-isolation smoke gates above are completed.
