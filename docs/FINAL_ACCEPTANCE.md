# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the repository and hosted service. It distinguishes repository CI, deployed runtime, and production operational readiness.

| Gate | Evidence status | Result |
|---|---|---|
| CI validation for deployed runtime commit | Main CI Run #584 completed successfully for commit `2a31c006a6e7e3174c6375c6f5226cb3430f373c`: PostgreSQL migration validation and Python 3.11–3.14 jobs, including security, container runtime, and wheel/sdist smoke | PASS |
| Latest deployed source commit | Render deployment `dep-db5s11tckfvc73b8ief0` for commit `2a31c006a6e7e3174c6375c6f5226cb3430f373c` reached `live` on 2026-10-11 | DEPLOYED |
| Runtime-code delta | The deployed commit updates acceptance documentation only; it does not change application runtime code relative to the previously validated runtime commit `dce34187ae3d4d14d35ece2fb049db4d1a38761e` | NO RUNTIME CHANGE |
| Hosted startup/readiness | Render logs show application startup complete and repeated `GET /ready` responses with `200 OK` after deployment `dep-db5s11tckfvc73b8ief0` | PASS (platform log evidence) |
| Migration schema coverage | Clean PostgreSQL 16 migration chain, `alembic current`, and `alembic check` pass in CI; live Render DB still has no `alembic_version` and has not been safely baselined or migrated | CI PASS / LIVE PENDING |
| Commercial entitlement enforcement | Package, offer, quotation batch, revision/resubmission, and document creation paths enforce plan limits and persist usage atomically | PASS (automated tests) |
| Commercial usage integrity | Manual usage writes are OWNER-only and PostgreSQL entitlement checks serialize on the organization subscription row | PASS (automated tests) |
| Security gate | Security commands and regression tests are part of the main CI gate | PASS |
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

Repository configuration alone is not execution evidence. A release claim is CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. Main CI Run #584 is confirmed successful for commit `2a31c006a6e7e3174c6375c6f5226cb3430f373c`. The Render deployment for that commit is live and the platform logs show readiness checks returning `200 OK`. This is **Main Green and deployed**, not proof of hosted production readiness.

The Render platform health-check path is `/ready`. This verification has platform-log evidence for successful readiness responses; it does not claim an independent external HTTP probe. The active environment configuration could not be safely confirmed from the available read-back. Do not switch the service to production mode until the database, migration, secrets, and recovery gates are ready.

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

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI Run #584 is confirmed successful for commit `2a31c006a6e7e3174c6375c6f5226cb3430f373c`; Render deployment `dep-db5s11tckfvc73b8ief0` for the same commit reached `live`, with repeated readiness `200 OK` log evidence. Hosted production remains unverified until durable database/recovery, production migration/configuration, billing-provider validation, and authenticated tenant-isolation smoke gates above are completed.
