# Hosted Pilot Acceptance Test Plan

**Status:** Prepared for owner approval; **no hosted workflow or tenant-isolation test has been executed by this document's author**.  
**Scope:** Controlled, synthetic-data acceptance of the currently deployed Industrial RFQ Intelligence API.  
**Decision boundary:** This plan does not authorize production writes, account creation, uploads, cleanup, deployment, or database access.

## 1. Preconditions — all required before any stateful hosted test

The owner must provide or confirm:

1. The approved target base URL and the exact deployed application commit/image from the hosting platform. A GitHub SHA or passing CI run is not deployment evidence.
2. Two owner-approved, separate test accounts for tenants A and B, with credentials delivered through an approved secret channel. Do not put credentials, bearer tokens, cookies, or full authorization headers in reports, shell history, screenshots, CI logs, or chat.
3. Written approval for synthetic organization/project/package creation, test uploads, expected rate-limited API usage, and the planned test window.
4. A named evidence custodian and approved location for sanitized response summaries, request IDs/timestamps, synthetic input hashes, output files, and cleanup records.
5. An approved cleanup/retention decision. The current API exposes no general-purpose DELETE route for these pilot objects. Do not invent a deletion endpoint or use direct production database commands. If no approved application-level cleanup path exists, retain the synthetic objects under clearly marked test names and record them for owner-managed cleanup.
6. Confirmation that the test uses only synthetic documents and values, not customer or supplier confidential data.

If any prerequisite is missing, mark the affected hosted tests **BLOCKED** and do not create or mutate records.

## 2. Evidence and result rules

Record separately:
- **Repository evidence:** code and automated tests at a specific commit.
- **CI evidence:** workflow URL, run number, exact tested head SHA, conclusion, and job results.
- **Hosted evidence:** deployment SHA/image from the hosting platform, timestamp, sanitized HTTP status/result, and request/correlation ID where available.
- **Owner/customer evidence:** approver, test-account authorization, witness/reviewer, and acceptance decision.

A `/health` or `/ready` success proves neither authentication nor tenant isolation. CI tests do not prove that the same code is deployed. Use **PASS** only when the expected result and supporting evidence are retained. Use **FAIL** for a reproduced defect, **BLOCKED** when authorization/prerequisites prevent execution, **PENDING** for a planned action awaiting a named approval/review, and **NOT VERIFIED** when no reliable execution evidence exists. Do not convert repository-level PASS into hosted PASS.

## 3. Current implementation contract to test

The following paths and limits are present in `src/freellmpool/api/app.py`, `src/freellmpool/api/auth.py`, and `src/freellmpool/api/schemas.py` on the reviewed main revision. Re-check against the owner-confirmed deployed revision before running the plan.

- Authentication: `POST /auth/login` returns a bearer access token; authenticated routes use `Authorization: Bearer <token>`. `GET /auth/me` returns the current user and organization memberships. Unauthenticated protected requests return HTTP 401 with `WWW-Authenticate: Bearer`.
- Tenant setup: `POST /organizations`, `POST /projects`, and `POST /packages`. Project creation verifies membership in the supplied organization. Package creation verifies membership in the project's organization and creates initial RFQ revision R1 from the supplied requirements.
- Quotation batch ingestion: `POST /packages/{package_id}/quotations/batch` is multipart form data with `entries` (a JSON array) and one `files` item per entry. The counts must match. Supported extensions are `.pdf`, `.txt`, and `.md`; each file is limited to 10 MB. The route validates the whole batch before persisting records and is intended to commit the batch atomically.
- Single quotation-document upload: `POST /offers/{offer_id}/documents`, multipart field `file`, with the same extension and 10 MB limits.
- Comparison and evidence: `GET /packages/{package_id}/comparison`, `GET /packages/{package_id}/technical-evaluation`, `GET /packages/{package_id}/evidence`, and `GET /documents/{document_id}`.
- Reports: `GET /packages/{package_id}/report` returns a machine-readable report; `GET /packages/{package_id}/report/markdown` returns the Markdown report.
- Other protected workflow paths include `/packages/{package_id}/workflow`, `/packages/{package_id}/decision`, `/packages/{package_id}/audit`, `/offers/{offer_id}/claims`, `/offers/{offer_id}/deviations`, `/packages/{package_id}/technical-lock`, `/packages/{package_id}/commercial-open`, and `/packages/{package_id}/evaluation-weighting`.
- Existing automated reference: `tests/test_auth_tenant.py` covers unauthenticated requests, same-tenant access, cross-tenant reads and mutations, quotation/document upload denial, and extended workflow/decision/report/usage paths. That is repository regression evidence, not hosted execution evidence.

## 4. Hosted test cases

Do not execute any stateful test below until all Section 1 prerequisites are approved.

### H-01 — Deployment identity and read-only readiness

**Prerequisite:** Owner confirms target URL and current deployed commit/image in the hosting platform.

**Action:** Capture the hosting-platform deployment identifier and commit/image. Then make read-only GET requests to `/health` and `/ready`.

**Expected:** `/health` returns HTTP 200 with service status `ok`; `/ready` returns HTTP 200 with `status=ready` and `database=ok`.

**Evidence:** Deployment page/sanitized identifier, UTC timestamp, HTTP status and response fields. Do not include secrets or customer data.

**Cleanup:** None; read-only.

**Result:** NOT VERIFIED until current hosted evidence is captured. A failed/unreachable probe is a failure or infrastructure blocker to investigate, not permission to change deployment settings.

### H-02 — Authentication and session handling

**Prerequisite:** Two approved test accounts; credentials stored only in an approved secret channel.

**Action:**
1. Request `GET /auth/me` without an Authorization header.
2. Request `GET /auth/me` with a deliberately invalid, non-secret bearer token.
3. Authenticate each approved account using `POST /auth/login` with its own email/password.
4. Use each returned token for `GET /auth/me`.

**Expected:** The first two requests return HTTP 401 and a Bearer challenge. Valid logins return HTTP 200; `/auth/me` returns the matching account and only that account's organization memberships. Never record token values. Do not conduct password spraying or repeated failure/rate-limit tests against the hosted service.

**Evidence:** Sanitized status codes, account labels A/B (not email addresses unless specifically approved), organization IDs, timestamp, and request IDs.

**Cleanup:** Revoke/expire sessions only through an approved application/owner procedure. Do not manipulate session rows directly.

### H-03 — Synthetic organization, project, and RFQ package creation

**Prerequisite:** H-02 passed; stateful writes and retention/cleanup explicitly approved.

**Action:** With account A, create a uniquely named test organization using `POST /organizations`; create a project using `POST /projects` with that organization ID; create a package using `POST /packages` with the project ID and synthetic requirements. Use an unambiguous run label such as `PILOT-ACCEPTANCE-<run-id>-A`. Repeat separately with account B only as needed for the isolation test.

**Synthetic requirement set:** R-01 rated voltage 415 V; R-02 output 75 kW; R-03 efficiency class IE3; R-04 enclosure IP55. The package payload includes `project_id`, `name`, `category`, `mode` (`STANDARD` or `PROJECT_EPC`), and `requirements` objects with `tag`, `parameter`, `required_value`, and optional `requirement_type`/`acceptance_rule`.

**Expected:** HTTP 201 for each create operation; returned IDs link the organization, project, package, and initial R1 RFQ revision. No other tenant IDs should appear in the response.

**Evidence:** Sanitized request bodies with synthetic values, status codes, returned object IDs, run label, and timestamp.

**Cleanup:** Use only the owner-approved procedure from Section 1. No DELETE endpoint is documented for these objects.

### H-04 — Quotation upload, validation, and atomicity

**Prerequisite:** H-03 passed; two synthetic quotation files prepared and reviewed.

**Action:** Submit `POST /packages/{package_id}/quotations/batch` as multipart form data: `entries` contains a JSON array of two quotation metadata objects, and `files` contains two matching synthetic files. Use only PDF, TXT, or Markdown, each below 10 MB. Vendor A should declare 415 V, 75 kW, IE3, IP55; Vendor B should declare 415 V, 75 kW, IE2, IP55. Include synthetic price/currency/lead-time/warranty values only.

Then perform negative validation checks with small synthetic requests: (a) an unsupported extension; (b) entries/files count mismatch; and (c) a duplicate vendor/revision. If explicitly approved and operationally safe, test the 10 MB boundary with synthetic data in a single isolated request.

**Expected:** Valid batch returns HTTP 201 and matching offer/document ID counts. Unsupported extension returns HTTP 415; count/schema mismatch returns HTTP 422; duplicate vendor/revision returns HTTP 409; oversized file returns HTTP 413. After each rejected batch, re-read the package's offers and confirm no partial offer/document/usage rows were added by the rejected request. Do not assume a content type alone proves file validity.

**Evidence:** Synthetic input filenames and SHA-256 hashes, file sizes, sanitized request metadata, response status, offer/document IDs from the valid batch, and before/after counts for negative cases. Do not retain uploaded binaries outside the approved evidence location.

**Cleanup:** Owner-approved application procedure or controlled retention as test artifacts. Do not delete records through direct SQL.

### H-05 — Technical comparison and deviation traceability

**Prerequisite:** H-04 passed; synthetic source files are available to the reviewer.

**Action:** Request `GET /packages/{package_id}/comparison`, `GET /packages/{package_id}/technical-evaluation`, and `GET /packages/{package_id}/workflow`. Inspect the Vendor B R-03 row. If extraction has not produced a claim for R-03, do not silently mark the requirement compliant: use the existing `POST /offers/{offer_id}/claims` workflow only after the source has been manually checked and the authorized test procedure specifies the appropriate claim status and source reference. If testing the explicit deviation workflow, use `POST /offers/{offer_id}/deviations` with a synthetic description and preserve the returned deviation ID.

**Expected:** R-01, R-02, and R-04 values are traceable to the corresponding uploaded document where extraction supports them. The IE2-versus-IE3 discrepancy is visible as a non-compliance/deviation or an explicitly unverified item requiring review; it must never be silently represented as a verified match. Human review remains mandatory; the application must not be treated as making the supplier decision.

**Evidence:** Sanitized comparison rows, R-03 status, source-document ID/filename/page/section where returned, deviation ID if created, and reviewer disposition. Preserve the original synthetic source hash.

**Cleanup:** Retain the result with the test package or use the approved owner cleanup procedure.

### H-06 — Evidence retrieval and report/export behavior

**Prerequisite:** H-04 passed; H-05 evidence captured.

**Action:** Request `GET /packages/{package_id}/evidence`, `GET /documents/{document_id}`, `GET /packages/{package_id}/report`, and `GET /packages/{package_id}/report/markdown` using account A's token.

**Expected:** HTTP 200 for A-owned objects. The evidence register and report should include the synthetic requirements/offers, source provenance that was actually extracted or manually recorded, and the IE2/IE3 discrepancy or an explicit review-needed status. JSON should parse as JSON; Markdown should return a non-empty report with the expected package/vendor content. No report may be described as an approved procurement decision.

**Evidence:** HTTP statuses, content types, output filenames/hashes, and sanitized excerpts for R-01–R-04. Store full reports only in the approved evidence location.

**Cleanup:** Keep reports under the same access/retention control as the synthetic test record; remove local temporary files securely after evidence is retained.

### H-07 — Cross-tenant read denial

**Prerequisite:** Two independent approved accounts A and B, each with a separate test organization; H-03 through H-06 completed for tenant A.

**Action:** Using B's token, request tenant A's package resources: `GET /packages/{A-package-id}/rfq`, `/offers`, `/comparison`, `/technical-evaluation`, `/evidence`, `/report`, `/report/markdown`, `/workflow`, `/decision`, `/audit`, and `GET /documents/{A-document-id}`.

**Expected:** Each foreign-object request returns HTTP 404, consistent with the implementation's non-disclosure behavior. Compare one known nonexistent resource with one foreign resource; status and detail should not reveal whether the foreign resource exists. Account A must still be able to retrieve its own objects.

**Evidence:** Sanitized route/method, status, response detail, test account label, object label, timestamp, and request ID. Do not log bearer tokens.

**Cleanup:** Read-only; no cleanup needed.

### H-08 — Cross-tenant write denial and non-mutation proof

**Prerequisite:** H-07 passed; owner specifically approves negative write requests.

**Action:** Using B's token, attempt one request each against A-owned resources: batch quotation ingestion at `POST /packages/{A-package-id}/quotations/batch`; single document upload at `POST /offers/{A-offer-id}/documents`; claim creation at `POST /offers/{A-offer-id}/claims`; decision creation at `POST /packages/{A-package-id}/decision`; technical lock at `POST /packages/{A-package-id}/technical-lock`; commercial open at `POST /packages/{A-package-id}/commercial-open`; and evaluation-weight update at `PUT /packages/{A-package-id}/evaluation-weighting`. Use small synthetic payloads. Do not send a valid batch/file unless the owner has approved the test and its expected rejection.

**Expected:** Each cross-tenant mutation returns HTTP 404. Re-read A's package, offer count, documents, comparison, audit events, and relevant workflow state with A's token; none should reflect B's attempted mutation. Do not interpret a 404 alone as sufficient: verify no side effect.

**Evidence:** Sanitized status codes, before/after object counts and relevant state, audit event comparison, timestamps, and request IDs.

**Cleanup:** Any unexpected mutation is a **FAIL**; stop further tests, preserve sanitized evidence, and notify the owner. Do not attempt improvised rollback or direct database repair.

### H-09 — Controlled cleanup and closeout

**Prerequisite:** All planned tests completed and evidence reviewed.

**Action:** Inventory all objects created under the unique run label, all uploaded synthetic documents, report exports, and temporary local files. Apply only the owner-approved cleanup method. If no application-level delete operation is available, record that the test objects remain and assign cleanup to the authorized owner; do not claim cleanup passed.

**Expected:** Evidence is retained in the approved location; no secrets or real customer data are present; each object is either removed by an approved mechanism or explicitly listed as retained with an owner and retention date.

**Evidence:** Final object inventory, evidence index, cleanup method/result, owner sign-off, and open defects.

## 5. Stop conditions

Stop the test immediately and mark the affected gate **FAIL** or **BLOCKED** if:
- deployment identity cannot be confirmed;
- an approved account accesses another tenant's object;
- a cross-tenant mutation returns success or changes state;
- an invalid upload leaves partial records;
- secrets or another tenant's data appear in logs or reports;
- a synthetic test could trigger real billing, supplier contact, notification, or external provider processing;
- cleanup would require an unapproved production database operation.

Do not merge a PR, trigger a deployment, change production configuration, or run production database commands as part of this plan.

## 6. Acceptance evidence register

| Gate | Required evidence | Initial result |
|---|---|---|
| Current deployed revision identified | Hosting-platform deployment ID plus exact SHA/image | NOT VERIFIED |
| Health/readiness | Timestamped read-only responses | NOT VERIFIED |
| Authentication | Sanitized 401/200 results for approved accounts | BLOCKED pending approved accounts |
| Synthetic package creation | Returned organization/project/package/R1 IDs | BLOCKED pending write approval |
| Quotation upload and rejection atomicity | Response codes and before/after counts | BLOCKED pending write approval |
| Technical deviation/provenance | Comparison, evidence register, source references, reviewer disposition | BLOCKED pending write approval |
| JSON/Markdown report retrieval | Status, content type, output hash, sanitized excerpts | BLOCKED pending write approval |
| Cross-tenant read denial | B-token negative reads and A-token positive controls | BLOCKED pending approved accounts and authorization |
| Cross-tenant write denial | Rejection responses plus non-mutation proof | BLOCKED pending explicit negative-write approval |
| Cleanup and retention | Object inventory and approved cleanup record | BLOCKED pending owner cleanup decision |
| Owner/customer acceptance | Named reviewer, date, decision, outstanding defects | NOT VERIFIED |

## 7. Repository/control-document synchronization dependency

The project-control files on `main` are not updated by this test plan. The current control-document refresh work overlaps the still-open PR #129 (`docs/PROJECT_CONTINUITY.md`, `docs/MARKET_LAUNCH_MASTER_PLAN.md`, and `docs/LAUNCH_ACCEPTANCE_MATRIX.md`). Do not edit those same files in parallel or assume PR #129 is merged.

After PR #129 is independently reviewed and its final status is known, perform a focused control-document reconciliation against then-current `main` and the actual open PR heads. Correct the baseline SHA/CI references and the P7-OPS-02 description without marking unmerged PR content as main-branch evidence. Keep hosted acceptance, deployment identity, backup/restore, and owner/customer sign-off at their evidence-supported statuses.
