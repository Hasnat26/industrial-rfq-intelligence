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

All of these endpoints require authentication and verify membership:
`/projects`, `/packages`, `/packages/{id}/rfq`, `/packages/{id}/offers`,
`/offers/{id}/revisions`, `/offers/{id}/claims`, `/offers/{id}/deviations`,
`/offers/{id}/clarifications`, `/deviations/{id}/resolve`,
`/clarifications/{id}/close`, `/offers/{id}/documents`, `/documents/{id}`,
`/offers/{id}/technical-status`, `/packages/{id}/technical-lock`,
`/packages/{id}/commercial-open`, `/packages/{id}/comparison`,
`/packages/{id}/evidence`. `/health` remains public for load-balancer checks.
Claims provenance continues to reject source documents belonging to a
different offer — and therefore to a different organization.

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

## Known limitations (deliberate scope cuts)

- No OAuth/OIDC/social login, no password reset flow, no email verification.
- Registration (`/auth/register`) is not IP-rate-limited; duplicate emails are
  rejected, but bulk account creation is an edge-infrastructure concern.
- Role granularity exists (`OWNER`/`ADMIN`/`MEMBER`) but all members
  currently have full access to their organization; per-role authorization
  rules are future work.
- Single active organization context per request is derived from resource
  ownership; there is no "switch organization" endpoint because resources
  already carry their tenant.
