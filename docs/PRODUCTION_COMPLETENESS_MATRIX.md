# V1 Production Completeness Matrix

This is the ranked implementation sequence for the Industrial RFQ Intelligence SaaS. A feature is considered complete only after implementation, regression coverage, documentation, and green CI.

## Priority 1 — Scanned-document intelligence
Status: IMPLEMENTED — CI validation in progress.

- Optional OCR for scanned/image-only PDF pages.
- Native text is retained for pages with sufficient machine-readable text.
- Sparse pages are rendered and OCRed with page-level provenance preserved.
- Explicit dependency boundary: PyMuPDF + Pillow + pytesseract plus a Tesseract executable.
- Regression coverage for non-PDF passthrough and missing OCR dependency failure.
- Follow-on: table extraction will build on this page-aware OCR layer.

## Priority 2 — Industrial table extraction
- PDF table detection and structured rows/cells.
- Excel and Word quotation ingestion.
- Cell-level evidence and provenance.
- Header/row normalization for engineering schedules.

## Priority 3 — Evidence viewer and source highlighting
- Document/page/section/table/cell evidence viewer.
- Click-through from compliance/deviation/claim to source evidence.
- OCR text/image coordinate references where available.
- Immutable evidence references.

## Priority 4 — Reviewer workflow UI
- Human review queue.
- Requirement-by-requirement technical review.
- Clarification/deviation resolution.
- Technical bid lock and commercial opening visibility.
- Explicit approval gates and review comments.

## Priority 5 — Background document-processing jobs
- Queue-backed ingestion/OCR/extraction jobs.
- Progress and failure states.
- Retry policy and dead-letter handling.
- Idempotent job execution.

## Priority 6 — Production object storage
- S3-compatible document/artifact storage.
- Database stores metadata and immutable references.
- Signed upload/download URLs.
- Retention and deletion policy.

## Priority 7 — Extraction confidence and model traceability
- Field-level extraction confidence.
- Model/provider/version metadata.
- Prompt/schema version.
- Extraction run ID and reproducibility metadata.
- Human override provenance.

## Priority 8 — Granular RBAC
- Owner, Procurement Manager, Engineering Manager, Technical Evaluator, Commercial Evaluator, Reviewer, Auditor, Vendor, Read-only.
- Permission matrix for read/create/update/approve/export/admin operations.
- Tenant isolation remains mandatory.

## Priority 9 — Revisioned extraction and review
- Immutable extraction runs.
- Review revisions and supersession.
- Diff between extraction/review versions.
- Reproducible report generation from a selected version.

## Priority 10 — Commercial normalization
- Currency normalization.
- Incoterms.
- Taxes/duties/freight.
- Payment terms.
- Delivery and warranty normalization.
- Optional items and exclusions.
- Normalized landed-cost view without autonomous supplier selection.

## Priority 11 — Explainable vendor evaluation
- Human-approved scoring criteria.
- Category-specific weighting.
- Technical/commercial score traceability.
- Every score linked to evidence and review decisions.
- No autonomous procurement award.

## Priority 12 — Observability and operational controls
- Structured logs with tenant/package/job correlation.
- Metrics and health/readiness endpoints.
- LLM latency/token/cost telemetry where provider exposes it.
- Queue depth and worker health.
- Alertable failure conditions.

## Priority 13 — Security hardening
- Session revocation/rotation.
- Rate limiting.
- Upload validation and malware scanning boundary.
- Signed URLs.
- Secret rotation.
- Encryption and secure configuration.
- Data export/deletion controls.
- Immutable audit integrity checks.

## Priority 14 — API and integration maturity
- Formal OpenAPI contract review.
- API versioning policy.
- SDK/client examples.
- Webhook/event contract.
- Integration test suite.

## Priority 15 — Production deployment and recovery
- Reference deployment topology.
- PostgreSQL + Redis/queue + workers + object storage.
- Container hardening.
- Backup/restore procedure.
- Migration safety.
- Disaster-recovery runbook.

## Priority 16 — Billing and commercial SaaS completion
- Subscription lifecycle.
- Provider-specific payment execution.
- Complete webhook event coverage.
- Entitlement reconciliation.
- Usage anomaly handling.
- Invoice/payment state visibility.

## Priority 17 — Procurement portal and analytics
- Vendor portal.
- Multi-project dashboard.
- Procurement KPI analytics.
- Category templates.
- Exportable management dashboards.

## Priority 18 — Procurement memory and lifecycle expansion
- Explicit manufacturer/model/product identity.
- Rich historical aggregation.
- PO/delivery/installation linkage.
- Performance, warranty, failure, maintenance and replacement intelligence.
- Historical comparisons remain decision support only.

## Completion gate

The project will be called "V1 complete" only after all selected priorities above are either implemented or explicitly deferred as non-V1 scope, with tests, documentation, security review, and green CI evidence. "100% complete" means complete against this agreed V1 scope, not that the product can never gain additional features.
