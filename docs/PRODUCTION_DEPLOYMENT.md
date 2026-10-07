# Production Deployment Runbook

This runbook describes the boundary between the repository and the external production environment for Industrial RFQ Intelligence.

## 1. Production boundary

The repository provides the SaaS application, deterministic RFQ evaluation, evidence/provenance handling, persistent multi-tenant data model, authentication/tenant controls, commercial entitlement controls, migrations, readiness checks, and container packaging.

The following are intentionally supplied by the deployment environment:

- managed PostgreSQL;
- database backups and tested restore capability;
- TLS/HTTPS and ingress;
- container/VM hosting;
- secret storage;
- object/binary storage if original documents ever become a retained product feature;
- billing-provider account and credentials;
- external monitoring/alerting.

The repository must not be described as a hosted production service until these external dependencies are provisioned and validated.

## 2. Required production configuration

Set:

- INDUSTRIAL_RFQ_ENV=production
- INDUSTRIAL_RFQ_DATABASE_URL to managed PostgreSQL
- INDUSTRIAL_RFQ_AUTO_CREATE_TABLES=0
- INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET to a strong secret of at least 32 characters
- INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET to a strong secret of at least 32 characters

The application deliberately fails closed when production is configured with SQLite, table auto-creation, or missing/weak billing/reconciliation secrets.

Use .env.example as the configuration reference. Never commit production credentials.

## 3. Database migration

From the repository root, with the production PostgreSQL URL available:

~~~
alembic upgrade head
~~~

The migration chain is the authoritative production schema mechanism. Do not use application table auto-creation as a production migration strategy.

Before applying migrations to an important environment:

~~~
alembic current
alembic heads
~~~

The expected state is a single current head corresponding to the checked-in migration chain.

## 4. Build and start

Build the dedicated SaaS image:

~~~
docker build -f Dockerfile.saas -t industrial-rfq-intelligence:0.1.0 .
~~~

For the supplied production compose boundary:

~~~
docker compose -f docker-compose.saas.production.yml up -d --build
~~~

The production image runs the API as a non-root user and exposes the FastAPI service on port 8000 inside the deployment boundary.

## 5. Readiness verification

Verify the application process and database separately:

~~~
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
~~~

Expected readiness response:

~~~
{"status":"ready","database":"ok"}
~~~

In the real deployment, expose the service through the TLS/HTTPS ingress and monitor the externally reachable readiness path through the platform's health-check mechanism.

## 6. Minimum authenticated smoke flow

After readiness is green, perform a small end-to-end smoke test:

1. register a test user;
2. authenticate;
3. create a test organization;
4. create a test project;
5. create a procurement package;
6. create one RFQ revision/requirement set;
7. create at least one vendor offer;
8. verify technical/commercial comparison;
9. retrieve evidence;
10. retrieve the Markdown report;
11. verify tenant isolation using a second organization/user.

The smoke test must confirm that a request for tenant A cannot read or mutate tenant B data.

## 7. Commercial entitlement smoke

For a plan with a deliberately small limit:

1. perform an allowed metered write;
2. verify the corresponding usage record is persisted;
3. perform the next write that exceeds the limit;
4. verify the API returns the expected entitlement rejection;
5. confirm usage is not over-counted by retries;
6. verify authorized reconciliation can repair an intentionally introduced mismatch.

Do not bypass the application by directly writing usage records except for controlled administrative repair; manual usage mutation is OWNER-only by design.

## 8. Billing boundary

Payment execution is intentionally provider-neutral in the repository. A production billing rollout must supply an external billing provider and connect its signed webhooks to the existing application-side billing boundary.

Before enabling paid plans:

- configure provider secrets outside source control;
- verify signature checking;
- verify event idempotency;
- test subscription activation;
- test renewal/period rollover;
- test cancellation;
- test payment failure;
- test webhook replay;
- test reconciliation after a deliberately missed or duplicated event.

Entitlement decisions remain server-side. A client-side payment state must never be treated as authoritative.

## 9. Backups and recovery

The application repository does not provide the production database backup service.

The deployment owner must define:

- backup frequency;
- retention window;
- encrypted backup storage;
- recovery-point objective (RPO);
- recovery-time objective (RTO);
- restore procedure;
- periodic restore testing.

A production launch is not considered operationally complete until a restore has been tested against the actual deployment stack.

## 10. Rollback

Prefer application rollback to the last known-good image when a release causes an application defect.

Do not automatically run a down migration as part of rollback. Database schema rollback is a separate controlled change and must be validated for data-loss risk before use.

For a failed deployment:

~~~
docker compose -f docker-compose.saas.production.yml ps
docker compose -f docker-compose.saas.production.yml logs --tail=200 industrial-rfq-api
~~~

Restore the previous known-good application image, confirm database compatibility, then re-run readiness and the authenticated smoke flow.

## 11. Security controls

Production must include:

- HTTPS/TLS;
- secret manager or equivalent protected secret storage;
- managed PostgreSQL access controls;
- restricted database network access;
- least-privilege deployment credentials;
- external rate limiting/shared state for multi-replica authentication protection;
- centralized logs without secrets or sensitive document content;
- routine dependency/security scans from CI.

The repository's security workflows and tests are a release gate, not a substitute for infrastructure security.

## 12. Document retention limitation

The current system persists extracted document text/pages and provenance rather than retaining original binary uploads as a durable document archive.

Do not advertise durable original-file retention until an explicit object-storage/retention design has been implemented and validated.

## 13. Release evidence

For each production release, record:

- exact Git commit SHA;
- GitHub Actions result for that SHA;
- migration head;
- container image identifier;
- deployment timestamp;
- readiness result;
- authenticated smoke result;
- backup/restore evidence;
- billing webhook verification result when billing is enabled.

A release should only be called **Hosted Production Green** after the deployment checks above pass. A GitHub Actions success alone is **Main Green**, not proof of hosted production readiness.
