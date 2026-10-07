# Pilot Launch Package

This checklist defines the first-customer pilot boundary for Industrial RFQ Intelligence. It is intentionally narrower than the full product roadmap so the pilot can validate customer value without introducing uncontrolled engineering or procurement authority.

## 1. Pilot use case

Primary pilot workflow:

**415 V Induction Motors & VFD Supply**

Customer supplies one RFQ/specification and two to five vendor quotations. The platform structures requirements and vendor responses, evaluates deterministic technical compliance, preserves evidence/provenance, surfaces deviations and unverified claims, and produces an engineer-readable review package.

The system is decision support. The customer's authorized engineer remains responsible for technical acceptance, commercial judgment, negotiation, supplier recommendation, and purchase approval.

## 2. Customer input package

Minimum pilot input:

- RFQ/specification;
- vendor quotations;
- available technical datasheets/catalogues;
- commercial quotation terms where available;
- vendor name/identity;
- any project-specific evaluation weighting or acceptance rules.

Preferred source formats are PDF, Excel, Word, Markdown, or text. Scanned PDFs can use the OCR ingestion capability where the deployment includes the required OCR runtime.

## 3. Pilot output package

The pilot should return:

1. normalized requirement set;
2. vendor-by-vendor technical comparison;
3. deterministic compliance classifications;
4. technical deviations and clarification needs;
5. commercial information/risk view;
6. evidence register with source/page provenance where available;
7. engineering review actions;
8. machine-readable JSON result;
9. engineer-readable Markdown report.

The product should never silently convert missing evidence into verified information.

## 4. Customer acceptance criteria

A pilot is successful when:

- the intended RFQ and quotations can be ingested;
- requirements and vendor claims are traceable;
- deterministic comparison results are reproducible;
- missing, contradictory, or unverified claims are surfaced;
- reviewers can identify the source evidence behind a result;
- tenant isolation prevents one customer's data from being exposed to another customer;
- the generated report is useful to the customer's engineering/procurement reviewer.

A pilot is not considered successful merely because an AI-generated summary looks plausible.

## 5. Human-control boundary

The platform must not be positioned as:

- an autonomous procurement authority;
- an engineering certification or approval system;
- an unattended plant-operation system;
- a substitute for qualified engineering review.

The customer must retain the final technical and procurement decision.

## 6. Pilot operating model

Recommended first-customer sequence:

**intake -> controlled upload -> automated extraction/comparison -> engineer review -> clarification loop -> report export -> customer feedback**

For the first pilots, keep a human operator involved in document-quality checks and evidence review. Record defects as reproducible cases that can become regression tests.

## 7. Commercial model boundary

The repository contains application-side subscriptions, usage metering, entitlement enforcement, reconciliation, and a provider-neutral billing boundary.

Actual payment collection is not treated as enabled until an external billing provider is configured and its signed webhook lifecycle is validated.

For the first pilot, a manual commercial agreement or invoice can be used outside the application while the billing execution integration is being finalized. Do not represent that as automated in-product payment.

## 8. Production prerequisites

Before calling the service **Hosted Production Green**, validate:

- managed PostgreSQL;
- Alembic migration state;
- production fail-closed configuration;
- `/health` and database-backed `/ready`;
- authenticated end-to-end smoke flow;
- tenant isolation;
- entitlement enforcement;
- backups and tested restore;
- TLS/HTTPS;
- external monitoring/alerting;
- rate limiting suitable for the actual replica topology;
- billing webhook verification when paid billing is enabled.

The exact operational procedure is in `docs/PRODUCTION_DEPLOYMENT.md`.

## 9. Pilot evidence record

For every pilot, record:

- customer/pilot identifier;
- product category;
- source document set identifier;
- application commit/image identifier;
- report identifier;
- reviewer;
- acceptance result;
- defects found;
- evidence/provenance defects found;
- follow-up engineering changes.

Do not store sensitive customer documents in public repositories or issue trackers.

## 10. Pilot-to-product feedback loop

Classify customer feedback into:

**P0 — correctness/safety:** incorrect deterministic comparison, tenant isolation failure, evidence/provenance loss, authorization failure, data corruption.

**P1 — workflow blocker:** customer cannot complete the intended RFQ workflow without a workaround.

**P2 — efficiency:** report quality, UI friction, extraction quality, search/retrieval improvements.

**P3 — expansion:** new product categories, richer analytics, integrations, additional billing options.

P0 issues block customer expansion. P1 issues should be prioritized before adding broad P3 features.

## 11. Launch discipline

Do not claim:

- public hosted availability before an actual deployment is validated;
- automated payment before a provider integration is operationally tested;
- durable original document retention while only extracted text/pages are retained;
- autonomous procurement decisions.

The fastest credible path is:

**one controlled pilot -> measured engineering value -> operational hardening -> billing execution -> first paid production customer -> broader expansion.**