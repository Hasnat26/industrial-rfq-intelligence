# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the current repository and hosted service state. Statuses below distinguish repository CI, deployment completion, and production operational readiness.

| Gate | Evidence status | Result |
|---|---|---|
| Last verified Main GitHub Actions green run | Main CI Run #577 completed successfully for commit `d98d258b49e65c3babf50ec2c45d5db473c731c8`: Python 3.11–3.14, PostgreSQL 16 migration validation, lint/type checks, security, container smoke, and wheel/sdist smoke | PASS |
| Latest deployed application commit | Render deployment `dep-db5o737lot8c73fkud90` for commit `d98d258b49e65c3babf50ec2c45d5db473c731c8` reached `live` on 2026-10-11; build and deploy events reported success | DEPLOYED |
| Latest commit combined status query | GitHub Actions Run #577 completed with conclusion `success` for the deployed commit | NOT CONFIRMED BY STATUS API |
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
| Hosted health/readiness | Render `healthCheckPath` is configured as `/ready`; user verified external `/health` returns `{"status":"ok","service":"industrial-rfq-intelligence"}` and `/ready` returns `{"status":"ready","database":"ok"}`. After deployment `d98d258b49e65c3babf50ec2c45d5db473c731c8`, Render app logs show repeated `GET /ready` responses with `200 OK` at 2026-10-11 12:41 UTC | PASS |
| Hosted production validation | Commit `d98d258b49e65c3babf50ec2c45d5db473c731c8` is live and readiness returned 200; production migration state, backups/restore, provider billing, and authenticated tenant-isolation smoke remain unverified | NOT YET GREEN |

## Acceptance rule

Repository configuration alone is not execution evidence. A release claim is CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. Main CI Run #577 is confirmed successful for deployed commit `d98d258b49e65c3babf50ec2c45d5db473c731c8`. This is Main Green, not proof of hosted production readiness.

A successful CI run is **Main Green**, not proof of hosted production readiness. Render's platform health-check path is now `/ready`. User-visible external checks returned successful `/health` and `/ready` JSON responses, and Render app logs show repeated `/ready` 200 responses after the setting was applied. The active environment configuration could not be read back in this verification pass; previously observed configuration indicated development mode with automatic table creation. Do not switch the service to production mode until the database, migration, secrets, and recovery gates are ready.

## Remaining production acceptance work

1. Provision durable managed PostgreSQL with restricted access, backups, and a tested restore procedure. The current Free staging database expires on 2026-11-08 and has no managed backups.
2. Apply and verify Alembic migrations against that database; keep automatic table creation disabled in production.
3. Configure strong production billing-webhook and reconciliation secrets using protected environment configuration.
4. Configure an actual billing provider and verify webhook signatures, idempotency, subscription lifecycle, and reconciliation before enabling paid plans.
5. Health-check configuration is complete: Render `healthCheckPath=/ready`; externally verified `/health` and `/ready` responses, with repeated Render `/ready` 200 log entries after deployment.
6. Execute authenticated end-to-end smoke tests, including organization/tenant isolation and entitlement enforcement.
7. Verify TLS/ingress, monitoring/alerts, rate limiting/shared state as needed, and backup/restore evidence.
8. Record the exact deployed commit, migration head, readiness output, smoke-test results, and recovery evidence.

## Portfolio-safe statement

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI Run #577 and the Render deployment of commit `d98d258b49e65c3babf50ec2c45d5db473c731c8` are confirmed successful. Hosted production remains unverified until durable database/recovery, production migration/configuration, billing-provider validation, and authenticated tenant-isolation smoke gates above are completed. Health-check configuration and live readiness are now verified.
