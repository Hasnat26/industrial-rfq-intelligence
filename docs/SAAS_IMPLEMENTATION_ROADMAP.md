# SaaS Implementation Roadmap

## P0 - Preserve and stabilize the engineering core

1. Keep the deterministic compliance and evidence model stable.
2. Add regression tests around current RFQ behavior.
3. Separate domain models from CLI concerns where practical.
4. Keep the existing local workflow runnable while the web layer is introduced.

## P1 - First usable SaaS vertical slice

**Status (authentication + tenancy + batch ingestion milestones):** persistent
database, organization/user model, web API, authentication, tenant isolation,
and the migration foundation are delivered. See `docs/SAAS_AUTH_AND_TENANCY.md`
for the architecture and migration workflow. Document storage/ingestion APIs,
atomic batch quotation ingestion (`POST /packages/{id}/quotations/batch`),
product-category configuration, browser review UI, and exportable report are delivered.

Target workflow:

Requirement -> Standard RFQ -> upload 2-5 vendor quotations -> normalize -> technical comparison -> commercial comparison -> review report.

Deliverables:

- persistent database;
- organization/user model;
- web API;
- authentication;
- tenant isolation;
- document upload/storage;
- batch quotation ingestion;
- product-category configuration;
- web review screen;
- exportable CS/TBE-style report.

## P2 - Project/EPC procurement workflow

**Status: Complete.** PROJECT_EPC now has controlled technical issue resolution, revision lineage, technical bid locking, commercial opening/evaluation, final human decision, workflow audit trail, and browser visibility.

Deliverables:

- project/package hierarchy;
- technical offer revisioning;
- clarification/deviation workflow;
- technical bid lock gate;
- commercial opening/evaluation gate;
- human-controlled final decision / approval record;
- audit trail.

## P3 - Procurement memory

**Status: Initial historical retrieval slice complete.** Procurement memory is now exposed as a read model over the canonical procurement ledger. It retrieves vendor history, product/category history, decision rationale, price/lead-time/warranty history, and reusable claim evidence without duplicating source records. Tenant-isolated search is available by vendor, category, package, and free-text query.

Deliverables:

- vendor history;
- product history;
- decision rationale history;
- price/lead-time/warranty history;
- reusable evidence;
- historical search and retrieval.

Historical information remains decision support, not an automatic procurement instruction. The next P3 increment should add explicit product/manufacturer/model identity and richer historical aggregation where the source workflow captures those fields.

## P4 - Lifecycle intelligence

Deliverables:

- installation/commissioning records;
- maintenance and failure history;
- warranty events;
- spare-part history;
- replacement history;
- lifecycle cost inputs.

## P5 - Commercial SaaS hardening

Deliverables:

- subscription plans;
- usage metering;
- billing/payment integration;
- API limits;
- observability;
- backups/recovery;
- security hardening;
- privacy/data-retention controls;
- production deployment.

## Immediate build priority

P0/P1/P2 are implemented and P3 now has its first usable historical-memory slice. The next revenue-oriented priority is to deepen P3 with explicit product identity and aggregated historical intelligence before moving to lifecycle intelligence or broad category expansion.
