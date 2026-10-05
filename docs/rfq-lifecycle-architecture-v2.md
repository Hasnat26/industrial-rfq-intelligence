# RFQ Intelligence Lifecycle Architecture v2

## Purpose

The system is a customer-controlled industrial procurement workflow that separates customer requirement definition, vendor technical evaluation, vendor clarification/resubmission, customer-approved RFQ refinement, technical lock, commercial evaluation, integrated evaluation, and human final decision.

The system provides evidence, traceability, comparison, scoring, and workflow controls. It does not autonomously reject or select suppliers.

## Canonical lifecycle

Customer Requirement
-> RFQ Revision R1
-> Technical Offers
-> Vendor-by-vendor Technical Evaluation
-> Vendor Clarification / Resubmission
-> Optional RFQ Gap Discovery
-> Customer Approval of RFQ Change
-> RFQ Revision R2
-> Re-evaluate all vendors against the new RFQ revision
-> Repeat until technically ready
-> Technical Lock
-> Commercial Offers
-> Commercial Evaluation
-> Integrated Evaluation
-> Human Final Decision

## Critical domain distinction

RFQ revision and vendor offer revision are different version chains.

RFQ:
- RFQ R1
- RFQ R2
- RFQ R3

Vendor A:
- Technical Offer R1 evaluated against RFQ R1
- Technical Offer R2 evaluated against RFQ R2

Vendor B:
- Technical Offer R1 evaluated against RFQ R1
- Technical Offer R2 evaluated against RFQ R2

A vendor revision must never silently change the RFQ baseline. Every technical evaluation must identify the exact RFQ revision used as its baseline.

## Proposed domain model

### ProcurementPackage

Represents the procurement event/workspace.

It owns RFQ revisions, vendor offer chains, evaluation settings, workflow state, audit history, and final decision.

### RfqRevision

First-class immutable version of the customer RFQ.

Suggested fields:
- id
- package_id
- revision
- status
- reason
- created_by_user_id
- created_at
- supersedes_revision_id

Rules:
- revision content is immutable after publication
- a new revision is created instead of mutating an old revision
- only one revision is the current active technical baseline
- publication/change is auditable

### RfqRequirement

Requirement belongs to an RfqRevision, not directly to the package.

Suggested fields:
- id
- rfq_revision_id
- tag
- parameter
- required_value
- requirement_type
- acceptance_rule
- sequence

This preserves historical requirement baselines.

### VendorOffer

Represents one technical offer revision.

Suggested fields:
- id
- package_id
- parent_offer_id
- vendor_key
- vendor_name
- technical_revision
- rfq_revision_id
- technical_status
- commercial_status
- source/document references

The rfq_revision_id is mandatory for a published technical offer.

### VendorClaim

A claim belongs to a specific VendorOffer revision. New vendor revisions produce new claims rather than overwriting old claims.

### TechnicalEvaluation

Future first-class evaluation snapshot.

Suggested fields:
- id
- package_id
- rfq_revision_id
- offer_id
- evaluation_status
- score
- evaluated_at
- evaluated_by_user_id
- engine_version

The first implementation may calculate deterministic comparisons on demand, but the model must allow auditable evaluation snapshots later.

### TechnicalGap

A derived finding from RFQ requirement, vendor offer, and evaluation result.

Possible classifications:
- MISSING
- UNCLEAR
- DEVIATION
- CONFLICT
- EVIDENCE_REQUIRED

A gap is not a rejection.

### TechnicalClarificationRequest

Customer-created communication record linked to a vendor offer/evaluation.

It contains vendor, RFQ revision, offer revision, gap IDs, request text, status, actor, and timestamps.

### CommercialOffer

Commercial data is logically separated from technical qualification. Commercial evaluation becomes available only after package technical lock.

## Technical evaluation semantics

For every requirement:

COMPLIANT — vendor evidence supports the RFQ requirement.

DEVIATION — vendor explicitly offers something different.

UNVERIFIED — vendor did not provide sufficient verifiable information.

CONFLICT — available evidence is contradictory.

No evidence must never be treated as compliance.

A technical clarification request is an action to resolve uncertainty; it is not a rejection.

## RFQ gap discovery

When review identifies a requirement that should apply to the project but was absent from the current RFQ:

1. Mark it as a proposed RFQ gap.
2. Customer reviews the proposed requirement.
3. Customer either rejects the proposal or approves it.
4. If approved, create a new RFQ revision.
5. Re-evaluate every vendor against the new RFQ revision.
6. Do not penalize a vendor for a requirement that was not part of the RFQ baseline used for its previous evaluation.

This is a central fairness and auditability rule.

## Technical lock gate

Technical lock is permitted only when the customer-controlled workflow has no blocking unresolved condition.

Examples:
- mandatory requirement unverified
- unresolved critical conflict
- unresolved major deviation
- open clarification affecting technical qualification
- vendor not evaluated against the current RFQ revision

After technical lock:
- RFQ technical baseline is frozen
- vendor technical submissions are frozen
- commercial evaluation may open
- technical weighting cannot be changed

Reopening technical evaluation must be an explicit controlled workflow and must trigger review of downstream commercial results.

## Commercial gate

Before technical lock:
- commercial offer data is locked/inaccessible to the evaluation workflow
- commercial scoring must not influence technical qualification

After technical lock:
- only technically eligible vendors enter commercial evaluation
- commercial values are compared
- currency comparability is validated
- commercial flags remain explicit

## Integrated evaluation

Integrated evaluation combines technical and commercial scores using customer-configured weights.

Example: Technical 70%, Commercial 30%.

Formula:

integrated = technical_score * technical_weight / 100
           + commercial_score * commercial_weight / 100

Technical and commercial gates remain independent. A weighting change must never bypass a technical gate.

## Human decision boundary

The platform may extract claims, compare values, identify gaps/deviations/conflicts, calculate scores, generate clarification requests, track revisions, generate reports, and recommend review actions.

The platform must not autonomously reject a supplier, approve a supplier, alter customer requirements, or select a final supplier.

Those are customer/engineering decisions.

## Implementation strategy

Block 0 — Architecture and data-model foundation
- RFQ revision model
- immutable requirement baseline
- migration strategy
- compatibility with existing packages

Block 1 — Technical comparison engine
- deterministic requirement-vendor comparison
- vendor-specific gap detection
- preserve existing revision behavior

Block 2 — Vendor clarification
- customer-ready gap checklist
- clarification request persistence
- audit trail

Block 3 — Vendor resubmission
- new technical offer revision
- document ingestion
- provenance-backed claims

Block 4 — RFQ refinement
- propose RFQ gap
- customer approval
- publish new RFQ revision
- apply revision to all vendors

Block 5 — Re-evaluation
- evaluate all current vendor offers against current RFQ revision
- identify stale evaluations
- resolve old/new gap state

Block 6 — Technical lock
- blocking-condition calculation
- controlled lock
- commercial gate

Block 7 — Commercial evaluation
- commercial offer intake
- eligible-vendor filtering
- commercial comparison

Block 8 — Integrated evaluation
- customer weighting
- deterministic technical/commercial score
- final review actions

Block 9 — Customer UI
- RFQ revision history
- vendor evaluation
- clarification
- resubmission
- RFQ refinement
- technical lock
- commercial evaluation
- final decision

Block 10 — Full regression and release gate
- full test suite
- Ruff
- strict mypy
- Python 3.11–3.14
- build/wheel smoke
- migration tests
- tenant-isolation tests

## Engineering rule

One block -> tests -> green -> freeze -> next block.

No feature block may be combined with another feature block merely to reduce commits.

If a regression appears, work stops on the current block until the regression is fixed and the relevant gate is green.
