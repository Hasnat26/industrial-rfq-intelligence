# SaaS Implementation Roadmap

## P0 - Preserve and stabilize the engineering core

1. Keep the deterministic compliance and evidence model stable.
2. Add regression tests around current RFQ behavior.
3. Separate domain models from CLI concerns where practical.
4. Keep the existing local workflow runnable while the web layer is introduced.

**Status: Complete.**

## P1 - First usable SaaS vertical slice

Authentication + tenancy + persistent database, web API, tenant isolation, document ingestion, atomic batch quotation ingestion, product-category configuration, browser review surfaces, and exportable reporting are implemented.

**Status: Complete.**

Target workflow:

Requirement -> Standard RFQ -> upload 2-5 vendor quotations -> normalize -> technical comparison -> commercial comparison -> review report.

## P2 - Project/EPC procurement workflow

PROJECT_EPC supports controlled technical issue resolution, revision lineage, technical bid locking, commercial opening/evaluation, final human decision, workflow audit trail, and browser visibility.

**Status: Complete.**

## P3 - Procurement memory

The procurement memory slice is implemented as a read model over the canonical procurement ledger. It retrieves vendor history, product/category history, decision rationale, price/lead-time/warranty history, and reusable evidence with tenant isolation. Product/manufacturer/model identity has also been added to the persistent model.

**Status: Complete for the current MVP scope.**

Historical information remains decision support, not an automatic procurement instruction.

## P4 - Lifecycle intelligence

Canonical lifecycle events, installed asset/product records, lifecycle cost inputs, asset-level lifecycle economics, reliability indicators, warranty exposure indicators, spare-part metrics, and replacement lifecycle metrics are implemented.

**Status: Complete for the current MVP scope.**

Lifecycle intelligence is derived from canonical dated events and cost records; it does not make autonomous maintenance or replacement decisions.

## P5 - Commercial SaaS hardening

The application-side commercial control plane is implemented:

- subscription and plan catalog;
- append-only usage ledger;
- server-side entitlement enforcement on metered write paths;
- provider-neutral subscription lifecycle;
- authenticated/idempotent billing webhook receipt;
- billing-event subscription synchronization;
- usage reconciliation;
- deterministic subscription-period rollover;
- authenticated reconciliation execution;
- anomaly detection;
- reconciliation audit trail and health state;
- scheduler-safe reconciliation runner;
- scheduler-ready commercial CLI;
- PostgreSQL-safe entitlement serialization;
- OWNER-only manual usage mutation.

**Status: Complete for application-side commercial controls.**

Actual payment collection/execution remains provider-neutral and requires an external billing provider, credentials, and deployment configuration. Managed PostgreSQL, backups/recovery, TLS/ingress, and production hosting are also deployment dependencies.

## P6 - Production deployment and market launch

P6 is the post-code-freeze track. The objective is to turn the current CI-green release candidate into an independently deployable pilot and then a paid production service without weakening the deterministic/evidence-first control model.

### P6.1 - Source-of-truth and operator documentation

- synchronize roadmap and acceptance records with the latest verified green state;
- maintain a production deployment runbook;
- define preflight, migration, readiness, rollback, backup, and incident procedures;
- explicitly separate repository capabilities from external deployment capabilities.

**Status: Complete.**

### P6.2 - Deployment validation

- provision managed PostgreSQL;
- apply Alembic migrations to head;
- build the SaaS image;
- verify /health and database-backed /ready;
- execute a minimal authenticated tenant/package/offer/report smoke flow;
- verify production fail-closed configuration;
- capture reproducible deployment evidence.

### P6.3 - Operational controls

- centralized application/container logs;
- external database backup and tested restore procedure;
- TLS/ingress;
- shared-store rate limiting for multi-replica deployments;
- alerting around readiness, error rate, database failures, billing webhook failures, and reconciliation anomalies.

### P6.4 - Billing execution

- select one supported billing provider;
- configure product/price identifiers;
- implement provider webhook verification against the existing provider-neutral boundary;
- test subscription activation, renewal, cancellation, payment failure, and replay/idempotency behavior;
- keep entitlement decisions server-side and fail-closed.

### P6.5 - Pilot launch package

- customer-facing quickstart;
- pilot RFQ sample package;
- technical-commercial report example;
- limitations and human-approval statement;
- support/incident contact procedure;
- first-customer onboarding checklist.

### P6.6 - Release gate

The release gate requires:

1. Main CI green for the exact release commit.
2. Production deployment smoke green.
3. Database migration state verified.
4. /ready green against managed PostgreSQL.
5. Authenticated tenant isolation smoke green.
6. Entitlement enforcement smoke green.
7. Billing webhook verification green when billing is enabled.
8. Backup/restore evidence recorded.
9. No unverified claim that the service is already publicly hosted.

## Priority order after the current code freeze

Do not add broad new product features before P6.2 unless a production validation discovers a blocking defect. The fastest route to revenue is:

**deployment -> real pilot workflow -> operational reliability -> billing execution -> first paid customer -> only then broader feature expansion.**
