# Engineering Decision Log

Material architectural and operational decisions, newest first. Each entry
records the decision, why, alternatives considered, and consequences. Related
documents: `docs/MARKET_LAUNCH_MASTER_PLAN.md` (backlog),
`docs/LAUNCH_ACCEPTANCE_MATRIX.md` (gates), `docs/FINAL_ACCEPTANCE.md`
(evidence table).

## D-015 — Backup-tooling P2-BK-02 closed at repository level (2026-10-12)

- **Decision:** treat P2-BK-02 as PASS for repository implementation and scratch-drill evidence after PR #117; keep live Render backup/restore as separate blocked gates P2-BK-03/04.
- **Evidence:** PR #117 merged as `57b63009e9d61c42d1849124382fe6217eceb983`; main CI Run #598 passed all five jobs. Runbook records scratch PostgreSQL drills and refusal paths.
- **Boundary:** CI and scratch drills do not demonstrate that the live Render database was backed up or restored. The owner must execute the live drill with actual credentials and a separate empty target.

## D-014 — Launch-control documents are the durable backlog (2026-10-12)

- **Decision:** `docs/MARKET_LAUNCH_MASTER_PLAN.md`,
  `docs/PROJECT_CONTINUITY.md`, `docs/LAUNCH_ACCEPTANCE_MATRIX.md`, and this
  file are the authoritative project-management system. Conversation history
  is not.
- **Why:** work alternates between Freebuff and ChatGPT sessions with no
  shared memory; the repository is the only shared durable surface.
- **Alternative rejected:** keeping the backlog in GitHub Issues — Issues are
  disabled in this repository's settings.
- **Consequence:** every work cycle must end with an updated
  `PROJECT_CONTINUITY.md` checkpoint.

## D-013 — Backup tooling must not require PATH changes and must use
independent restore connections (2026-10-12)

- **Decision:** the backup/restore scripts locate PostgreSQL tools via an
  explicit parameter / `PGBIN` / standard installation directories before
  falling back to PATH, and accept a fully independent restore-drill
  connection (host, port, user, password, database). A live server identity
  check (`port` + `pg_postmaster_start_time()`) must prove the restore target
  is not the source server before any restore.
- **Why:** the owner's Windows laptop has PostgreSQL 18.6 outside PATH, and
  the source is a remote Render instance that must never be restored over —
  including through a second network interface or IPv4/IPv6 alias, which a
  hostname-only comparison misses.
- **Alternatives rejected:** requiring a system-wide PATH edit (modifies the
  user's machine for one script); reusing the source connection for the drill
  (makes source/target separation a naming convention instead of a verified
  fact).
- **Consequence:** tooling works on the laptop unchanged; drills target
  local/test databases only.

## D-012 — Backup verification depth: schema metadata + row counts, TLS
required (2026-10-12, PRs #114/#115)

- **Decision:** restore drills compare table/column inventories, view/index/
  constraint definitions, Alembic revision state, and per-table row counts;
  both scripts require a TLS-enforcing `PGSSLMODE` (default `verify-full`);
  archives are published only after `pg_restore --list` validation, with
  SHA-256 recorded.
- **Why:** a dump that restores and matches structurally is the practical
  definition of a usable backup; plaintext connections to a production
  database are unacceptable.
- **Consequence:** row-count matching is explicitly documented as an
  operational check, not proof of byte-identical rows (see
  `docs/DB_BACKUP_RUNBOOK.md` "Verification semantics").

## D-011 — Migration strategy: Alembic forward-only, no live stamping
(2026-10-11)

- **Decision:** the Alembic chain is the sole production schema mechanism;
  CI validates `upgrade head` + `check` on clean PostgreSQL 16; the live
  database must not be stamped, reset, or migrated until its schema has been
  audited against the chain in an approved change window.
- **Why:** the live Render database reportedly lacks `alembic_version`; any
  stamping without an audit risks silent data/schema divergence.
- **Consequence:** P1-DB-01/02 remain BLOCKED on owner access; rollback is
  restore-based, which makes backups (P2-BK-*) a migration prerequisite.

## D-010 — Database baseline: keep Render Free plan, expiry is a hard
deadline (2026-10-12 re-affirmed)

- **Decision:** hosting stays on the Free plan. The recorded Free PostgreSQL
  expiry (2026-11-08) must be re-checked in the Render dashboard; any paid
  tier or migration requires explicit owner approval. No second Render Free
  database may be assumed available for drills — restore drills target a
  local/scratch database instead.
- **Consequence:** P1-DB-04 is an owner-gated deadline task; drill design is
  independent of Render provisioning.

## D-009 — Billing: pilot launches on manual commercial model (2026-10-11)

- **Decision:** the first pilot runs on a manual agreement/invoice outside
  the application; the provider-neutral billing boundary, entitlements,
  reconciliation, and webhook idempotency stay implemented but unexecuted
  until a provider is chosen with owner approval.
- **Why:** no provider account/credentials exist; claiming live payment
  verification without a real provider would be false evidence.
- **Consequence:** commercial-production gates C1/C2 stay BLOCKED; the pilot
  gate set excludes payments.

## D-008 — Security scanning relies on the CI gate; standalone workflows
disabled (2026-10-12)

- **Decision:** Bandit, pip-audit, zizmor, and the security-exceptions
  validator run inside every main CI job. The standalone `Security` and
  `CodeQL` workflows are `disabled_fork` and cannot be enabled by the
  repository App token (HTTP 403) — an owner action, tracked as P0-CI-02.
- **Consequence:** scanning is not absent, but CodeQL findings are not being
  produced; recorded as PARTIAL in the acceptance matrix (G15).

## D-007 — Coverage-gate contract is inconsistent and must be reconciled
(2026-10-12)

- **Decision:** record the conflict rather than silently pick a side:
  `AGENTS.md` describes `scripts/check_coverage.py` as a blocking gate, while
  `tests/test_ci_config.py` asserts CI must NOT invoke it. CI currently
  collects coverage only for the industrial core.
- **Next:** task P0-CI-03 chooses one contract and aligns docs, tests, and CI.

## D-006 — Original uploads are not retained (2026-10-10)

- **Decision:** only extracted text and page records persist; temporary
  upload files are deleted after parsing.
- **Consequence:** any claim of original-document retention requires object
  storage first (acceptance matrix C5 LIMITATION).

## D-005 — Production configuration fails closed (2026-10-10)

- **Decision:** production startup rejects SQLite URLs,
  `INDUSTRIAL_RFQ_AUTO_CREATE_TABLES`, and missing/short billing and
  reconciliation secrets (≥32 chars). Automated in
  `tests/test_release_config.py`.

## D-004 — Deployment topology: single dedicated FastAPI container,
`/ready` as health check (2026-10-09)

- **Decision:** Render runs `Dockerfile.saas` on port 8000; platform health
  checks use the database-backed `/ready`; `/health` is process liveness
  only. Readiness success is never treated as workflow proof.

## D-003 — Evidence-first claim model (2026-10-05)

- **Decision:** claims without explicit evidence stay `UNVERIFIED`;
  structured provenance (source/page/section/table/cell) is preserved;
  deterministic compliance classification never infers missing provenance;
  conflicting claims surface as contradictions. See
  `docs/EVIDENCE_POLICY.md`.

## D-002 — Deterministic classification separated from LLM extraction
(2026-09-23)

- **Decision:** LLM output is extraction assistance only; compliance
  decisions are deterministic Python; the system never autonomously selects a
  vendor and never operates plant equipment.

## D-001 — Multi-tenant data model with organization-scoped access
(2026-10-06)

- **Decision:** every repository-scoped query joins through the
  organization's membership check; cross-tenant identifiers return 404.
  Enforced by `tests/test_auth_tenant.py` (21 tests). Documented in
  `docs/SAAS_AUTH_AND_TENANCY.md`.
