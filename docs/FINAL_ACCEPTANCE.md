# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the current repository and hosted service state. Statuses below distinguish repository CI, deployment completion, and production operational readiness.

| Gate | Evidence status | Result |
|---|---|---|
| Last verified Main GitHub Actions green run | Main CI Run #560 completed successfully across Python 3.11–3.14, lint/type checks, security, container smoke, and wheel/sdist smoke (per recorded run evidence) | PASS |
| Latest deployed application commit | Render deployment for commit `55d29d51329602b9590e9f12b9ff2ad05e76edce` reached `live`; deployment events reported build and deploy success on 2026-10-09 | DEPLOYED |
| Latest commit combined status query | GitHub combined-status query returned no status entries for the deployed SHA; do not interpret an empty status list as a new CI pass | NOT CONFIRMED BY STATUS API |
| Migration schema coverage | Full current persistent schema is covered and package evaluation settings has an Alembic revision | PASS |
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
| Hosted health/readiness | Render service has no platform `healthCheckPath` configured; recent request-log query returned no entries, so external `/health` and `/ready` responses are not verified | NOT YET GREEN |
| Hosted production validation | Deployed commit is updated to `55d29d51329602b9590e9f12b9ff2ad05e76edce`, but production migration state, backups/restore, provider billing, and authenticated tenant-isolation smoke remain unverified | NOT YET GREEN |

## Acceptance rule

Repository configuration alone is not execution evidence. A release claim is CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. Main CI Run #560 is recorded as successful for the deployed commit; the latest combined-status API query returned an empty status list and is not independent confirmation of that run.

A successful CI run is **Main Green**, not proof of hosted production readiness. The current Render service is configured without a platform health-check path. Previously observed service configuration also indicated development mode with automatic table creation; the active environment configuration could not be read back in this verification pass. Do not switch the service to production mode until the database, migration, secrets, and recovery gates are ready.

## Remaining production acceptance work

1. Provision durable managed PostgreSQL with restricted access, backups, and a tested restore procedure. The current Free staging database expires on 2026-11-08 and has no managed backups.
2. Apply and verify Alembic migrations against that database; keep automatic table creation disabled in production.
3. Configure strong production billing-webhook and reconciliation secrets using protected environment configuration.
4. Configure an actual billing provider and verify webhook signatures, idempotency, subscription lifecycle, and reconciliation before enabling paid plans.
5. Configure the Render platform health-check path to `/ready`, then verify externally reachable `/health` and `/ready` responses. This setting was not changed during this pass.
6. Execute authenticated end-to-end smoke tests, including organization/tenant isolation and entitlement enforcement.
7. Verify TLS/ingress, monitoring/alerts, rate limiting/shared state as needed, and backup/restore evidence.
8. Record the exact deployed commit, migration head, readiness output, smoke-test results, and recovery evidence.

## Portfolio-safe statement

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI Run #560 and the Render deployment of commit `55d29d51329602b9590e9f12b9ff2ad05e76edce` are recorded as successful. Hosted production remains unverified until the external infrastructure, billing, recovery, readiness, and authenticated smoke gates above are completed.
