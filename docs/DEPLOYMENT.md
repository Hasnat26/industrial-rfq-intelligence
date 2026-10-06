# Industrial RFQ Intelligence SaaS Deployment

## Runtime

The SaaS API is the FastAPI application exposed by `industrial-rfq-api`, not the legacy CLI container. Build it with `Dockerfile.saas` or run `industrial-rfq-api` directly. The container listens on port 8000 and exposes `/ready` for database readiness checks.

## Production configuration

Set `INDUSTRIAL_RFQ_DATABASE_URL` to managed PostgreSQL in production and run `alembic upgrade head` as a deployment step before starting the application. Production startup fails closed unless the database URL uses PostgreSQL, `INDUSTRIAL_RFQ_AUTO_CREATE_TABLES` is not enabled, and both `INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET` and `INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET` are configured with at least 32 characters.

For a Compose-based production deployment, use `docker-compose.saas.production.yml`. It intentionally has no SQLite/database or secret defaults, so an incomplete production environment fails before the service starts. PostgreSQL, TLS/ingress, backups/recovery, and secret storage remain deployment-platform responsibilities.

Do not enable `INDUSTRIAL_RFQ_AUTO_CREATE_TABLES` in production. The application deliberately does not mutate non-SQLite schemas during startup.

## Local smoke deployment

Use:

    docker compose -f docker-compose.saas.yml up --build

This compose file explicitly runs in development mode with SQLite so the documented smoke path is reproducible without external infrastructure. Then verify `/ready` returns HTTP 200. Create a user through `POST /auth/register`, authenticate through `POST /auth/login`, create an organization, project, package, and ingest vendor quotations.

It is not a production database topology. Production should use `docker-compose.saas.production.yml` with PostgreSQL and managed backups/recovery.

## Storage boundary

Uploaded quotation documents are parsed into database-backed extracted text and page records. Temporary upload files are deleted after parsing. The current implementation does not retain original binary documents in object storage, so deployments requiring original-file retention should add object storage before making that claim.

## External billing

Payment collection remains provider-neutral. A production billing provider and credentials are required before charging customers. The authenticated/idempotent webhook boundary and subscription state model are implemented independently of provider execution.
