# Authentication, Multi-Tenancy, and Migrations

This document describes the authentication and tenant-isolation architecture
delivered in the *Authentication + Multi-Tenant Organization Isolation +
Database Migration Foundation* milestone, plus the migration workflow and test
strategy.

Core principle: **AI reads and structures. Deterministic rules compare.
Evidence explains. Workflow controls the sequence. Engineers decide.**
Authentication and tenancy wrap that engine in a per-organization boundary;
they do not change its semantics.

## Authentication architecture

### Models

| Table | Purpose |
| --- | --- |
| `users` | Registered accounts: `email` (unique, case-folded), `password_hash`, `is_active`. |
| `organization_memberships` | The tenant boundary: `(organization_id, user_id, role)` with a unique constraint per pair. Roles: `OWNER`, `ADMIN`, `MEMBER`. |
| `auth_sessions` | Opaque bearer tokens. Only the SHA-256 digest (`token_hash`) is stored; the plaintext token exists exactly once, in the login response. |

### Endpoints

| Endpoint | Auth | Notes |
| --- | --- | --- |
| `POST /auth/register` | none | Creates a user. Passwords are hashed with PBKDF2-HMAC-SHA256 (390,000 iterations, 16-byte random salt). Duplicate email → `409`. |
| `POST /auth/login` | none | Returns `{access_token, token_type, user}`. Wrong email or password → `401` with `WWW-Authenticate: Bearer` (identical response for both cases). |
| `GET /auth/me` | bearer | Current user plus organization memberships and roles. |
| `POST /organizations` | bearer | Creates an organization and grants the creator the `OWNER` membership in the same transaction. |
| everything else below | bearer | See isolation rules. |

### Session handling

- Tokens are `secrets.token_urlsafe(32)` (256 bits of entropy).
- Sessions expire after 24 hours (`SESSION_TTL_HOURS`).
- Lookup is by SHA-256 digest; expired, unknown, or inactive-user tokens →
  `401`.
- Password verification is constant-time (`hmac.compare_digest`), and login
  against a missing user still performs a hash computation so response timing
  does not reveal whether an email is registered.
- No plaintext password is ever stored or logged.

This is deliberately the simplest production-sane pattern (opaque bearer
tokens, no OAuth/OIDC, no third-party auth service). It is extensible: JWT or
SSO can be added later without changing the tenancy model.

## Organization / tenant model

```
Organization
    ├── OrganizationMembership -> User
    ├── Project
    │     └── ProcurementPackage
    │           ├── Requirement
    │           └── VendorOffer
    │                 ├── VendorClaim
    │                 ├── TechnicalDeviation
    │                 ├── TechnicalClarification
    │                 └── VendorDocument
    │                       └── VendorDocumentPage
```

Every organization-owned resource reaches its organization through this
hierarchy (`offer -> package -> project -> organization`). The membership
table is the only authority on who may see which organization.

## Tenant isolation rules

Server-side enforcement, applied to **every** existing endpoint (not only new
ones):

1. The user is derived solely from the bearer token. The client cannot
   assert an identity.
2. Each resource fetch is paired with a membership check:
   `is_member(db, user.id, resource.organization_id)`.
3. `organization_id` / `project_id` values supplied in request bodies are
   *proposals*, never authorization. `POST /projects` accepts an
   `organization_id` only if the authenticated user is a member of that
   organization; otherwise `404`. Editing request JSON cannot move a user
   into another tenant.
4. Missing resources and cross-tenant resources are indistinguishable: both
   return `404` with the same detail (e.g. `"package not found"`). This
   avoids IDOR probing — an attacker cannot confirm that another
   organization's package exists.
5. Membership is checked **before** workflow gates, so cross-tenant callers
   learn nothing from `409` gate responses (technical lock, commercial
   opening, revision rules, etc.).

### Status code policy

| Condition | Code |
| --- | --- |
| No/invalid/expired token | `401` + `WWW-Authenticate: Bearer` |
| Resource does not exist, **or** exists in another organization | `404` |
| Workflow gate violation (lock, commercial open, duplicate offer, …) | `409` |
| Validation failure | `422` |

### Coverage

All tenant-owned objects are addressed through the same guard:
`db.get(<Entity>, id)` followed by
`is_member(db, user.id, <entity>.org-chain .organization_id)` → `404` on none.
Completed full sweep (2026-10-15, P4-AUTH-03 audit of every path-parameter
endpoint in `src/freellmpool/api/app.py`):

| Guard chain | Endpoints |
| --- | --- |
| `ProcurementPackage` → `.project.organization_id` | `/packages/{id}/rfq`, `/offers`, `/decision` (GET+POST), `/audit`, `/workflow`, `/assets`, `/lifecycle-events`, `/lifecycle-costs`, `/lifecycle-intelligence`, `/cost-summary`, `/technical-evaluation`, `/comparison`, `/decision-support`, `/evaluation-weighting` (GET+PUT), `/integrated-evaluation`, `/engineering-decision-summary`, `/evidence`, `/report`, `/report/markdown` (via `package_report`), `/rfq-revisions`, `/quotations/batch`, `/technical-lock`, `/commercial-open` |
| `VendorOffer` → `.package.project.organization_id` | `/offers/{id}/revisions`, `/claims`, `/deviations` (GET+POST), `/clarifications` (GET+POST), `/documents`, `/technical-status`, `/technical-resubmission`, `/technical-clarification-request`, `/commercial-status` |
| `VendorDocument` → offer → package → org | `/documents/{id}` |
| `TechnicalDeviation` → offer → package → org | `/deviations/{id}/resolve` |
| `TechnicalClarification` → offer → package → org | `/clarifications/{id}/answer`, `/clarifications/{id}/close` |
| `Organization`/allocation objects | `/organizations/{id}/subscription` (GET+PUT), `/subscription/rollover`, `/usage` (GET/POST), `/usage/reconciliation`, `/billing/webhooks`, `/assets`, `/lifecycle-events`, `/lifecycle-cost-summary` |
| Static reference data (not tenant-owned) | `/product-categories/{category_key}` — global catalog templates, authenticated, no tenant objects |
| Unauthenticated by design | `/health`, `/ready` — no tenant data |

Cross-tenant 404 behavior for every non-static row above is exercised by
`tests/test_auth_tenant.py` (26 tests on merged main, including the completed
offer-scoped sweep for `technical-resubmission`, `technical-clarification-request`,
and `clarifications/{id}/answer`, the cross-tenant authorization matrix, and the
product-category route boundary). Claims provenance continues to reject source
documents belonging to a different offer — and therefore to a different
organization.

## Database migration workflow

Schema changes are delivered with **Alembic** (`alembic>=1.14`, a runtime
dependency). The initial revision `b088bb588596` represents the full current
schema (13 tables).

Migrations always target `INDUSTRIAL_RFQ_DATABASE_URL` (default:
`sqlite:///./industrial_rfq.db`), so PostgreSQL deployments driven by the same
variable are migrated with the same commands.

```bash
# apply all pending migrations
alembic upgrade head

# create a new revision after editing src/freellmpool/api/db.py
alembic revision --autogenerate -m "describe the change"

# adopt an existing development database created before Alembic
alembic stamp head

# inspect / roll back
alembic history
alembic downgrade base
```

### Startup behavior

`init_db()` on application startup only calls `create_all(checkfirst=True)`,
and only for SQLite (development) databases or when
`INDUSTRIAL_RFQ_AUTO_CREATE_TABLES=1` is set explicitly. It never drops or
recreates existing tables. Production (non-SQLite) databases are **not**
touched at startup: run `alembic upgrade head` as a deployment step instead.

## Local development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run the API (SQLite file at ./industrial_rfq.db)
industrial-rfq-api

# create the first development organization + user explicitly
python scripts/bootstrap_dev_user.py \
    --email owner@example.com \
    --organization "Demo EPC" \
    --password dev-password-123

# log in
curl -s localhost:8000/auth/login \
    -H 'content-type: application/json' \
    -d '{"email":"owner@example.com","password":"dev-password-123"}'

# then call APIs with: -H "Authorization: Bearer <access_token>"
```

The bootstrap script is intentionally **not** a backdoor: it refuses to run
when `INDUSTRIAL_RFQ_ENV=production`, never overwrites an existing password,
and is not invoked by application startup. Production environments register
users through `POST /auth/register` under their own operational controls.

## Test strategy

| File | Coverage |
| --- | --- |
| `tests/test_auth_tenant.py` | Registration, login success/failure/unknown user, unauthenticated rejection of every protected endpoint, forged/invalid tokens, plaintext-free password and token storage, same-tenant success path, and the cross-tenant matrix: reads, mutations, documents, workflow actions, and client-supplied `organization_id` attempts. |
| `tests/test_migrations.py` | Clean-database upgrade, upgrade→downgrade→upgrade round trip, adoption of a pre-existing development schema (`stamp`) without data loss, application startup against a migrated database (health + auth + org creation), and the production no-auto-create rule. |
| `tests/test_api.py` | Existing procurement workflow regression (PROJECT_EPC gates, technical lock, commercial opening, documents, evidence, revisions) — now exercised through an authenticated client. |
| `tests/test_procurement_domain.py`, `tests/test_industrial_demo.py`, `tests/test_industrial_report.py` | Domain and engineering-engine regression; unchanged by this milestone. |

Run everything:

```bash
pytest                 # full CI test scope
ruff check .
mypy --follow-imports=skip src/freellmpool/industrial.py src/freellmpool/industrial_report.py
mypy src/freellmpool/api src/freellmpool/procurement_domain.py
```

## Abuse controls (session lifecycle, rate limiting)

- **Failed-login rate limiting**: `/auth/login` keeps a sliding-window
  failure budget per normalized email (`INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES`,
  default 5) and per client IP (`INDUSTRIAL_RFQ_LOGIN_IP_MAX_FAILURES`, default 25)
  over `INDUSTRIAL_RFQ_RATE_LIMIT_WINDOW_SECONDS` (default 300). Exhausted budgets
  return `429` with `Retry-After` *before* any password verification; a successful
  login clears the email budget. The limiter is in-process (see below).
- **Expired-session pruning**: issuing a new session deletes that user's
  already-expired `auth_sessions` rows in the same transaction, so stale rows
  cannot accumulate. Expired tokens are additionally rejected at every request.
- **Timing-safe internal secrets**: the `/commercial/internal/*` reconciliation
  endpoints compare their shared secret with `hmac.compare_digest` (billing
  webhooks already did).
- **Deployment boundary**: the in-process limiter assumes a single application
  process. Multi-worker or multi-replica deployments must enforce a shared
  failure budget at the edge (reverse proxy or shared store); that integration
  is documented here rather than faked with a local-only counter.
- **General write-path policy**: all authenticated write endpoints
  (`POST/PUT/PATCH`, e.g. `/organizations`, `/projects`, `/packages`,
  `/packages/{id}/offers`, `/offers/{id}/claims`, decision/support,
  revision/lifecycle and commercial endpoints) are deliberately **not**
  throttled by the in-process failure limiter. Their abuse exposure is bounded
  by narrower controls at four layers: (1) bearer authentication with expired-
  and inactive-session rejection on every request; (2) per-organization
  entitlement and quota checks that serialize on the subscription row and
  persist usage atomically, so unbounded writes require a paid plan first
  (P6-BILL-01 / acceptance gate G13); (3) provider-call size/deadline caps for
  LLM/OCR paths (P5-SEC-01); (4) reconciliation and internal endpoints require
  timing-safe shared secrets. For the single-replica Free-tier topology this
  is the documented policy: credential-limited endpoints are throttled in
  process; sustained authenticated write abuse must be mitigated at the edge
  (platform request throttling or a shared-store limiter). **Limitation**:
  the in-process limiter is per-process and resets on restart; adding
  workers/replicas without an edge or shared-store limiter invalidates both
  the failure budgets above and any future write-path throttling, so scale-up
  must add an edge limiter (P7-OPS-04 monitoring should alert on sustained
  401/429 volume as the interim signal).

## Known limitations (deliberate scope cuts)

- No OAuth/OIDC/social login, no password reset flow, no email verification.
- Registration (`/auth/register`) failure budgets are email- and IP-scoped
  (`INDUSTRIAL_RFQ_REGISTRATION_*` env settings); duplicate emails are
  rejected, and bulk account creation beyond the failure windows remains an
  edge-infrastructure concern.
- Role granularity exists (`OWNER`/`ADMIN`/`MEMBER`) but all members
  currently have full access to their organization; per-role authorization
  rules are future work.
- Single active organization context per request is derived from resource
  ownership; there is no "switch organization" endpoint because resources
  already carry their tenant.
