# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the repository and hosted service. It distinguishes repository CI, deployed runtime, and production operational readiness.

| Gate | Evidence status | Result |
|---|---|---|
| Latest Main GitHub Actions run | Main CI Run #582 completed successfully for commit `c4fcdd3b730f967ba712642243cf3a7e82d87a3e`: Python 3.11–3.14, PostgreSQL migration validation, lint/type checks, security, container smoke, and wheel/sdist smoke | PASS |
| Latest deployed application commit | Render deployment `dep-db5ohc3bc2fs739jgfdg` for commit `dce34187ae3d4d14d35ece2fb049db4d1a38761e` reached `live` on 2026-10-11; build and deploy events reported success | DEPLOYED |
| CI evidence for deployed runtime | Main CI Run #580 completed successfully for deployed commit `dce34187ae3d4d14d35ece2fb049db4d1a38761e` | PASS |
| Latest documentation commit deployment | Commit `c4fcdd3b730f967ba712642243cf3a7e82d87a3e` contains acceptance documentation only; Render deploy list does not show it deployed. Runtime code is unchanged by this documentation commit | NOT DEPLOYED / NO RUNTIME CHANGE |
| Migration schema coverage | Clean PostgreSQL 16 migration chain, `alembic current`, and `alembic check` pass in CI; live Render DB still has no `alembic_version` and has not been safely baselined or migrated | CI PASS / LIVE PENDING |
| Commercial entitlement enforcement | Package, offer, quotation batch, revision/resubmission, and document creation paths enforce plan limits and persist usage atomically | PASS |
| Commercial usage integrity | Manual usage writes are OWNER-only and PostgreSQL entitlement checks serialize on the organization subscription row | PASS |
| Security gate | Security commands and regression tests are part of the main CI gate | PASS |
| Package/CLI smoke | Main CI includes wheel/sdist build and installation smoke | PASS |
| SaaS readiness surface | Dedicated FastAPI container, readiness endpoint, deployment instructions, local compose smoke surface, OCR runtime, and container CI smoke are present | PASS |
| Original binary document retention | Original uploads are intentionally not retained; only extracted text/pages are persisted | LIMITATION |
| Production payment execution | Provider-neutral billing boundary exists; provider credentials/execution are still required | EXTERNAL DEPENDENCY |
| Production fail-closed configuration | Production rejects SQLite, table auto-creation, and missing/weak billing/reconciliation secrets | PASS |
| Production PostgreSQL runtime | PostgreSQL DBAPI driver is packaged with the SaaS runtime dependencies | PASS |
| Production database | Current Render PostgreSQL is a Free staging database that expires on 2026-11-08 and has no managed backup; durable managed PostgreSQL and tested backup/recovery are still required | NOT YET GREEN |
| Hosted health/readiness | Render `healthCheckPath` is configured as `/ready`; user previously verified external `/health` and `/ready` JSON responses. Render app logs after deployment `dce34187ae3d4d14d35ece2fb049db4d1a38761e` show repeated `GET /ready` responses with `200 OK` | PASS (log evidence) |
| Hosted production validation | The deployed runtime is `dce34187ae3d4d14d35ece2fb049db4d1a38761e`; production migration state, backups/restore, provider billing, and authenticated tenant-isolation smoke remain unverified | NOT YET GREEN |

## Acceptance rule

Repository configuration alone is not execution evidence. A release claim is CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. Main CI Run #582 is confirmed successful for documentation commit `c4fcdd3b730f967ba712642243cf3a7e82d87a3e`. Main CI Run #580 is confirmed successful for the currently deployed runtime commit `dce34187ae3d4d14d35ece2fb049db4d1a38761e`. This is Main Green, not proof of hosted production readiness.

The Render platform health-check path is `/ready`. Render logs show repeated readiness `200` responses after the latest runtime deployment. The active environment configuration could not be read back in this verification pass; previously observed configuration indicated development mode with automatic table creation. Do not switch the service to production mode until the database, migration, secrets, and recovery gates are ready.

## Remaining production acceptance work

1. Provision durable managed PostgreSQL with restricted access, backups, and a tested restore procedure. The current Free staging database expires on 2026-11-08 and has no managed backups.
2. Audit and compare the live database schema with a clean restored backup. The live database is currently IP-allowlisted, so the hosted Render query connector cannot connect. Do not widen database access to the public internet just to enable the connector.
3. Establish the correct Alembic baseline only after schema equivalence is verified; then apply and verify migrations with automatic table creation disabled in production. Do not stamp or migrate the live database before this audit and an approved change window.
4. Configure strong production billing-webhook and reconciliation secrets using protected environment configuration.
5. Configure an actual billing provider and verify webhook signatures, idempotency, subscription lifecycle, and reconciliation before enabling paid plans.
6. Execute authenticated end-to-end smoke tests, including organization/tenant isolation and entitlement enforcement.
7. Verify TLS/ingress, monitoring/alerts, rate limiting/shared state as needed, and backup/restore evidence.
8. Record the exact deployed commit, migration head, readiness output, smoke-test results, and recovery evidence.

## Portfolio-safe statement

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI Run #582 is confirmed successful for documentation commit `c4fcdd3b730f967ba712642243cf3a7e82d87a3e`; the current live Render runtime is commit `dce34187ae3d4d14d35ece2fb049db4d1a38761e`, verified by Main CI Run #580 and Render deployment evidence. Hosted production remains unverified until durable database/recovery, production migration/configuration, billing-provider validation, and authenticated tenant-isolation smoke gates above are completed.
