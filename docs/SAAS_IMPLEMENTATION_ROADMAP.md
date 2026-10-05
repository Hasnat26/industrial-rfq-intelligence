# SaaS Implementation Roadmap

## P0 - Preserve and stabilize the engineering core

1. Keep the deterministic compliance and evidence model stable.
2. Add regression tests around current RFQ behavior.
3. Separate domain models from CLI concerns where practical.
4. Keep the existing local workflow runnable while the web layer is introduced.

## P1 - First usable SaaS vertical slice

**Status (authentication + tenancy milestone):** persistent database,
organization/user model, web API, authentication, tenant isolation, and the
migration foundation are delivered. See `docs/SAAS_AUTH_AND_TENANCY.md` for
the architecture and migration workflow. Document storage/ingestion APIs are
in place; batch quotation ingestion, product-category configuration, the web
review screen, and the exportable report remain open product work.

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

Deliverables:

- project/package hierarchy;
- technical offer revisioning;
- clarification/deviation workflow;
- technical bid lock gate;
- commercial opening/evaluation gate;
- approval workflow;
- audit trail.

## P3 - Procurement memory

Deliverables:

- vendor history;
- product history;
- decision rationale history;
- price/lead-time/warranty history;
- reusable evidence;
- historical search and retrieval.

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

Do not implement the entire platform at once. The first revenue-oriented slice should prove one complete customer workflow end-to-end before adding lifecycle intelligence or broad product-category coverage.
