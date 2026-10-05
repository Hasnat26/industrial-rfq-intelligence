# SaaS Canonical Data Model

This document defines the initial logical data model for the future SaaS application. It is intentionally storage-agnostic.

## Organization and access

### Organization
- id
- name
- tenant_key
- plan
- status

### User
- id
- organization_id
- name
- email
- role
- status

Users and all organization-owned records must be tenant-scoped.

## Procurement

### Project
- id
- organization_id
- project_code
- name
- client
- status

### ProcurementPackage
- id
- project_id
- package_code
- category
- mode (STANDARD or PROJECT_EPC)
- status

### Requirement
- id
- package_id
- tag
- parameter
- required_value
- requirement_type (MANDATORY, PREFERRED, OPTIONAL)
- acceptance_rule
- unit
- source_evidence_id

### RFQ
- id
- package_id
- revision
- generated_from_requirement_set
- technical_closing_date
- commercial_opening_date
- status

### Vendor
- id
- organization_id
- legal_name
- aliases
- contact_reference
- approval_status

### TechnicalOffer
- id
- rfq_id
- vendor_id
- document_reference
- revision
- status

### CommercialOffer
- id
- rfq_id
- vendor_id
- technical_offer_id
- price
- currency
- lead_time
- warranty
- payment_terms
- status

Commercial offers must be associated with the relevant technical offer/revision so the system can enforce the technical-gate workflow.

## Evaluation

### TechnicalEvaluation
- id
- technical_offer_id
- evaluator_id
- status
- score_or_status_summary
- completed_at

### Deviation
- id
- technical_offer_id
- requirement_id
- offered_value
- deviation_type
- disposition
- evidence_id

### Clarification
- id
- technical_offer_id
- requirement_id
- question
- vendor_response
- status
- evidence_id

### CommercialEvaluation
- id
- commercial_offer_id
- evaluator_id
- status
- risk_flags
- completed_at

### Decision
- id
- package_id
- selected_vendor_id
- rationale
- technical_basis
- commercial_basis
- approved_by
- approved_at

## Lifecycle

### PurchaseOrder
- id
- package_id
- vendor_id
- po_number
- po_date
- final_value
- currency

### AssetProduct
- id
- organization_id
- manufacturer
- model
- category
- serial_or_tag
- purchase_order_id

### LifecycleRecord
- id
- asset_product_id
- event_type
- event_date
- description
- evidence_id

Event types include INSTALLATION, COMMISSIONING, PERFORMANCE, WARRANTY, MAINTENANCE, FAILURE, SPARE_PART, REPLACEMENT and OTHER.

## Evidence

### Evidence
- id
- organization_id
- source_type
- source_name
- document_reference
- page
- section
- table
- cell
- excerpt_reference
- claim_status

Evidence is first-class and must be reusable across evaluations and lifecycle records.

## Historical intelligence

Historical procurement knowledge should support queries such as:

- what was purchased previously for this application;
- which vendors were evaluated;
- why a vendor was selected;
- what deviations were accepted;
- what price/lead time/warranty was obtained;
- how the asset performed after purchase;
- what failures or warranty issues occurred;
- what was eventually replaced and why.

Historical information is decision support, not an automatic procurement instruction.
