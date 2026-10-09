# Final Acceptance Gate

## Current status

This document records executable acceptance evidence for the current repository state.

| Gate | Evidence status | Result |
|---|---|---|
| Last verified Main GitHub Actions green run | Main commit `b13a07f326fc863ee64d925cc29aa2d976cad4c9`, CI Run #558 completed successfully across Python 3.11–3.14 | PASS |
| Latest verified PR CI | PR #101 CI Run #557 and post-merge Main Run #558 completed successfully across Python 3.11–3.14 | PASS |
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
| Hosted production validation | Render still runs commit `79afbd60ecef476e30fa1411cc6c296980b18c7b`; production migration state, backups/restore, provider billing, and authenticated tenant-isolation smoke remain unverified | NOT YET GREEN |

## Acceptance rule

Repository configuration alone is not execution evidence. A release claim is considered CI-verified only when a real GitHub Actions run for the relevant commit has completed successfully. The latest verified main commit is `b13a07f326fc863ee64d925cc29aa2d976cad4c9`, with Main CI Run #558 completed successfully across Python 3.11–3.14.

A successful CI run is **Main Green**, not proof of hosted production readiness. The current Render service is configured in development mode with automatic table creation, so it must not be described as production-ready.

## Remaining production acceptance work

1. Provision durable managed PostgreSQL with restricted access, backups, and a tested restore procedure.
2. Apply and verify Alembic migrations against that database; keep automatic table creation disabled in production.
3. Configure strong production billing-webhook and reconciliation secrets using protected environment configuration.
4. Configure an actual billing provider and verify webhook signatures, idempotency, subscription lifecycle, and reconciliation before enabling paid plans.
5. Run the production container against the managed database and verify `/health` and `/ready`.
6. Execute authenticated end-to-end smoke tests, including organization/tenant isolation and entitlement enforcement.
7. Verify TLS/ingress, monitoring/alerts, rate limiting/shared state as needed, and backup/restore evidence.
8. Record the exact deployed commit, migration head, readiness output, smoke-test results, and recovery evidence.

## Portfolio-safe statement

The repository contains an inspectable, evidence-aware industrial RFQ decision-support SaaS MVP with persistent multi-tenant data, deterministic comparison controls, provenance handling, human-review boundaries, lifecycle intelligence, commercial entitlement enforcement, authenticated billing boundaries, migration coverage, and a reproducible FastAPI deployment surface. Main CI is green on commit `b13a07f326fc863ee64d925cc29aa2d976cad4c9`. Hosted production remains unverified until the external infrastructure, billing, recovery, and authenticated smoke gates above are completed.
