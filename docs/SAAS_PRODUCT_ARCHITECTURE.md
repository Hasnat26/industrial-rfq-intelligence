# SaaS Product Architecture

## Product direction

Industrial RFQ Intelligence is evolving from a local evidence-aware RFQ review workflow into a multi-stage industrial procurement decision-support SaaS.

The product must support both standardized purchases and project/EPC procurement where vendor technical solutions may legitimately vary and commercial evaluation follows technical bid closure.

## Core principle

**AI reads and structures. Deterministic rules compare. Evidence explains. Workflow controls the sequence. Engineers decide.**

## Procurement modes

### Standard procurement

Requirement -> Standard RFQ -> Vendor quotations -> Normalization -> Technical/commercial comparison -> Human decision.

### Project/EPC procurement

Project requirement -> RFQ package -> Technical offers -> Technical evaluation -> Clarification/deviation resolution -> Technical bid lock -> Commercial evaluation -> Negotiation -> Final recommendation -> Purchase order.

Commercial evaluation must not be treated as final before the technical gate is closed.

## Product lifecycle

Customer requirement -> RFQ -> Vendor response -> Technical evaluation -> Commercial evaluation -> PO -> Delivery -> Installation/commissioning -> Performance -> Warranty -> Maintenance -> Failure/after-sales -> Replacement/repeat purchase.

The SaaS should preserve this chain as organizational procurement memory.

## Product intelligence model

The platform is product-category aware. Evaluation schemas and rules vary by category (for example motor, VFD, PLC, instrument, valve, switchgear) while the surrounding workflow remains common.

A product offer may be technically equivalent to the requirement even when brand/model/specification differs. The system must therefore distinguish:

- exact match;
- technically equivalent/acceptable subject to review;
- minor deviation;
- major deviation;
- clarification required;
- not compliant;
- unverified.

The AI may identify candidate equivalency evidence, but human engineering approval remains authoritative.

## Standard RFQ generation

The system should accept structured or unstructured customer requirements and generate a standardized RFQ package containing technical requirements, commercial terms, response schedule and evidence/attachment references.

Vendors remain free to respond in their own formats. The system normalizes PDF, Excel, Word and email-derived content into a canonical internal representation.

## Canonical procurement entities

- Organization
- User
- Project
- ProcurementPackage
- Requirement
- RFQ
- Vendor
- TechnicalOffer
- CommercialOffer
- Clarification
- Deviation
- TechnicalEvaluation
- CommercialEvaluation
- Decision
- PurchaseOrder
- Asset/Product
- InstallationEvent
- PerformanceRecord
- WarrantyRecord
- MaintenanceEvent
- FailureEvent
- LifecycleRecord
- Evidence

## SaaS boundary

The existing Python engineering/compliance engine is the reusable domain core. The SaaS application layer will add persistence, authentication, tenant isolation, workflow state, web UI, API, billing and operational controls around that core.

## Explicit non-goals

The platform is not an autonomous purchasing authority, engineering certification system, or plant-control system. Final technical and procurement decisions remain with authorized human users.
