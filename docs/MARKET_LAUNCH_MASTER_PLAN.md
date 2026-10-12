# Market Launch Master Plan

Authoritative remaining-work backlog for taking Industrial RFQ Intelligence from
the current CI-green release candidate to a controlled pilot and then commercial
production.

- Evidence links: `docs/LAUNCH_ACCEPTANCE_MATRIX.md` (gate-by-gate results),
  `docs/PROJECT_CONTINUITY.md` (resume checkpoint),
  `docs/ENGINEERING_DECISION_LOG.md` (recorded decisions).
- Status vocabulary: **PASS** (verified with linked evidence), **FAIL** (verified
  broken), **IN PROGRESS** (actively being executed), **BLOCKED** (requires
  owner credentials/approval/infrastructure), **NOT VERIFIED** (no execution
  evidence exists; never treat as PASS).
- Rules: repository CI is never sufficient proof of hosted behavior. Never run
  `alembic stamp head`, destructive migrations, or restore over the source
  database. Never widen the database allowlist to `0.0.0.0/0`. Never provision
  paid resources without explicit owner approval.

## Verified baseline (2026-10-12)

- `main` HEAD: `fe44588116f6d1afb0a7c70a0a3b661ec3db6593`.
- Main CI Run #624 (`38237349041`) SUCCESS on `fe44588116f6d1afb0a7c70a0a3b661ec3db6593` — <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38237349041>.
- PR #119 is closed/superseded; PR #124 is listed open, and PRs #128 and #129 remain open/unmerged. PR #128 is independent of P5-SEC-04 and was not modified. P5-SEC-01 remains CI-verified. P5-SEC-04 has repository-level fixes and synthetic regression tests in PR #129; code/test Run #631 passed all five jobs. Hosted validation remains NOT VERIFIED. Issues are disabled in repository settings.
- Last recorded Render deployment: `2a31c006a6e7e3174c6375c6f5226cb3430f373c` (deployment `dep-db5s11tckfvc73b8ief0`, recorded live 2026-10-11). Current hosted deployment was not re-verified during P5-SEC-04; do not infer deployment of PR #129 from CI.
- Hosted probes 2026-10-12: `/health` 200 and `/ready`
  `{"status":"ready","database":"ok"}` from an external HTTP client.

---

## P0 — CI and release-candidate integrity

### P0-CI-01 — Green required CI on release candidate
- Priority: P0. Status: **PASS**.
- Evidence: Run #594 (`38204840114`) success for `2f26234`, jobs
  `industrial (3.11–3.14)` and `postgres-migrations`.
- Definition of done: latest `main` commit has a fully successful CI run.
- Next action: refresh after every merge (routine).

### P0-CI-02 — Standalone Security and CodeQL workflows are disabled
- Priority: P0. Status: **FAIL** (verified disabled).
- Evidence: GitHub API reports workflows `Security` (371474370) and `CodeQL`
  (371474354) in state `disabled_fork`; enabling via the repository App token
  returns HTTP 403.
- Mitigation in place: the main CI `Security gate` step runs Bandit, pip-audit,
  and zizmor on every push/PR. CodeQL does not run at all.
- Autonomy: requires owner (GitHub Settings → Actions → enable workflows), or
  explicit acceptance of CI-only scanning recorded in the decision log.
- Definition of done: both workflows active with a passing run, or a recorded
  owner decision to rely on the CI security gate.
- Next action: owner enables the workflows in GitHub settings.

### P0-CI-03 — Coverage-gate contract mismatch
- Priority: P1. Status: **NOT VERIFIED** (contract inconsistency).
- Evidence: `AGENTS.md` describes a blocking coverage gate
  (`scripts/check_coverage.py` before PR), but
  `tests/test_ci_config.py::test_ci_has_no_legacy_coverage_gate_contract`
  asserts CI must NOT run that command. CI collects coverage for the industrial
  core only.
- Action: decide whether the 80/70 package thresholds are enforced locally,
  enforced in CI, or retired; make docs, tests, and CI agree.
- Autonomy: autonomous decision + docs/CI change once decided. Owner only if a
  new blocking CI gate is chosen.

### P0-CI-04 — Deployed commit vs main runtime code
- Priority: P0. Status: **PASS**.
- Evidence: no runtime-code delta between deployed `2a31c00` and `2f26234`
  (`git diff --stat 2a31c00..2f26234 -- src/ migrations/ Dockerfile*` empty).

---

## P1 — Live database integrity and migration baseline

### P1-DB-01 — Live schema vs intended schema comparison
- Priority: P0 for launch. Status: **BLOCKED**.
- Blocker: live Render PostgreSQL is IP-allowlisted; comparison requires the
  owner's allowlisted laptop connection. Live DB reportedly has no
  `alembic_version` table (not re-verified this cycle).
- Required action (owner): from the allowlisted machine, using the merged
  backup tooling, capture `alembic current`/`alembic heads` and a schema
  inventory; store evidence in `docs/evidence/`.
- Explicit prohibitions: no `alembic stamp head`, no schema reset, no data
  modification to resolve uncertainty. A failed connection is not evidence of
  corruption.
- Dependencies: P2-BK-02 (tooling must be laptop-ready first).
- Definition of done: written comparison of live schema vs `alembic upgrade
  head` output on scratch PostgreSQL, with discrepancies listed.

### P1-DB-02 — Migration baseline decision
- Priority: P0 for launch. Status: **BLOCKED** (depends on P1-DB-01).
- Action: only after P1-DB-01 proves equivalence (or documents exact gaps),
  approve and schedule a change window to establish the baseline and run
  `alembic upgrade head` with `INDUSTRIAL_RFQ_AUTO_CREATE_TABLES=0`.
- Rollback: migrations are forward-only; rollback = restore from backup into a
  fresh instance (hence P2-BK-03/BK-04 are prerequisites).

### P1-DB-03 — Migration chain verified on clean PostgreSQL
- Priority: P0. Status: **PASS**.
- Evidence: `postgres-migrations` CI job (Run #594) runs `alembic upgrade
  head`, `alembic current`, `alembic check` on PostgreSQL 16.

### P1-DB-04 — Durable database before Free-instance expiry (2026-11-08)
- Priority: P0 (deadline-driven). Status: **BLOCKED / OWNER DECISION**.
- Facts: the recorded Render Free PostgreSQL expires 2026-11-08 with no managed
  backup or PITR. Current provider state (plan, expiry, billing) must be
  re-checked in the Render dashboard; it cannot be verified from the repo.
- Options requiring owner approval: paid Render PostgreSQL, or export/migrate
  to another provider's free tier (accepting migration work and allowlist
  changes).
- Consequence of delay: data loss at expiry; pilot and any production claim
  become impossible.
- Next action: owner re-checks Render dashboard state and selects an option;
  record the decision in `docs/ENGINEERING_DECISION_LOG.md`.

---

## P2 — Backup, restore, and data recovery

### P2-BK-01 — Backup scripts with archive + schema verification
- Priority: P0. Status: **PASS** (repository level; PRs #114/#115).
- Evidence: custom-format dump, `pg_restore --list` TOC validation, SHA-256
  checksum, schema metadata comparison (tables/columns/views/indexes/
  constraints/Alembic state), per-table row-count comparison, TLS-required
  (`PGSSLMODE`), refusal to restore into the source database, offline
  regression tests in `tests/test_backup_restore_safety.py`.

### P2-BK-02 — Laptop-ready tooling: tool-directory detection + independent
restore connection + live server identity guard
- Priority: P0. Status: **PASS** (repository code + scratch drill; PR #117 merged).
- The former gap is closed: the merged scripts locate tools explicitly, use an independent restore connection, and verify live server identity. The owner's Windows laptop has
  PostgreSQL 18.6 in `C:\Program Files\PostgreSQL\18\bin` **not on PATH**, and
  the drill must target a **separate local database with an independent
  connection** (different host/port/user/password allowed). The scripts must
  also verify, from the live server identity (`port` +
  `pg_postmaster_start_time()`), that the restore target is not the source
  server reachable through another interface.
- Evidence: PR #117 adds tool detection, independent target credentials, recreate-drill option, source/target identity guard, version checks, refusal tests, and runbook updates. CI Run #598 passed. Scratch PostgreSQL drill evidence is documented in `docs/DB_BACKUP_RUNBOOK.md`.
- Acceptance criteria: tools resolve without PATH changes; connections independently configurable; source-target collisions refused by config and live identity; P2-BK-01 checks preserved; runbook matches.
- Autonomy: fully autonomous (scratch infrastructure only).

### P2-BK-03 — Live Render backup with owner credentials
- Priority: P0. Status: **BLOCKED** (owner laptop + credentials).
- The exact procedure is in `docs/DB_BACKUP_RUNBOOK.md`. Credentials must never
  be pasted into chat. The archive must be created from the real Render
  database; only then may it be recorded as backed up.
- Definition of done: timestamped `.dump` + `.toc.txt` + `.sha256` produced
  from the live database, retained in two protected encrypted locations.

### P2-BK-04 — Live restore drill into an isolated target
- Priority: P0. Status: **BLOCKED** (depends on BK-03; owner laptop; requires a
  separate pre-created empty target — never the source).
- Definition of done: restore completes with all P2-BK-01 verification checks
  passing against the live-derived archive; evidence recorded.

### P2-BK-05 — Recovery documentation and evidence retention
- Priority: P1. Status: **PARTIAL** (`docs/DB_BACKUP_RUNBOOK.md` current;
  live evidence pending BK-03/BK-04).

---

## P3 — Core business workflow

### P3-WF-01 — RFQ end-to-end workflow coverage
- Priority: P1. Status: **PASS** at the automated-test level for the main
  paths (intake, revision control, quote ingestion, extraction/normalization,
  technical evaluation, commercial comparison, review, export) — see
  `tests/test_api.py`, `tests/test_block1_technical_comparison.py`,
  `tests/test_engineering_decision.py`,
  `tests/test_integrated_evaluation.py`, `tests/test_commercial.py`.
- Hosted execution: **NOT VERIFIED** (tracked as P4-AUTH-02).

### P3-WF-02 — Adversarial/edge-case matrix
- Priority: P1. Status: **NOT VERIFIED** (partial coverage only).
- Specific gaps to test and close: incomplete quotations, conflicting
  revisions, missing specifications, unit normalization failures, malformed
  files, parser/OCR failure modes, extraction uncertainty propagation.
- Acceptance criteria: each case has a regression test asserting the failure
  is surfaced to the reviewer and never silently upgraded to a verified claim
  (see `docs/EVIDENCE_POLICY.md`).
- Autonomy: autonomous.

---

## P4 — Authentication, authorization, and tenant isolation

### P4-AUTH-01 — Two-tenant API isolation test suite
- Priority: P0. Status: **PASS** (automated).
- Evidence: `tests/test_auth_tenant.py` (21 tests): cross-tenant reads and
  mutations blocked, extended cross-tenant sweeps, session lifecycle
  (expiry/inactive user purge), registration/login rate limiting per
  account and IP, password spraying defense, client-supplied organization id
  cannot switch tenant.

### P4-AUTH-02 — Hosted tenant-isolation smoke against the deployment
- Priority: P0 for pilot. Status: **NOT VERIFIED**.
- Action: with owner-approved test accounts and clearly-labeled test data on
  the hosted service, run the authenticated smoke flow from
  `docs/PRODUCTION_DEPLOYMENT.md` section 6 plus a cross-tenant negative test.
- Autonomy: requires owner-created test accounts or explicit approval to
  register test accounts on production.

### P4-AUTH-03 — Systematic object-level access (IDOR) sweep
- Priority: P1. Status: **PARTIAL**.
- Evidence: tenant guards exist on package/offer/quotation/document paths and
  the client-supplied organization-id attack is tested; a full endpoint-by-
  endpoint identifier-manipulation audit with recorded results is missing.
- Action: enumerate all path-parameter endpoints, verify each enforces
  tenant-scoped lookup (404 on foreign objects), add tests for any gaps.
- Autonomy: autonomous.

---

## P5 — Security and operational reliability

### P5-SEC-01 — Prompt-injection resistance for RFQ documents
- Priority: P1. Status: **PASS (repository regression tests; hosted attack testing NOT VERIFIED)**.
- Evidence: PR #122 merged as `656781d2f4761d4a77a43ee93be74d671f6a0b61`; PR CI Run #611 passed all five jobs on `4e3e0420a815c9c3eec0e662f6be24e05e231925`.
- Changes: RFQ/quotation text is JSON-encoded and delimited as untrusted input; extraction instructions explicitly forbid following instructions embedded in document content. RFQ, per-quotation, combined quotation, and model response limits are enforced before/after gateway calls. Four synthetic regression tests cover prompt injection and size limits.
- Boundary: prompt instructions are a mitigation, not a formal guarantee against every model behavior; output is still strictly validated locally. No live hosted adversarial test was executed.
- Next: consider hosted synthetic attack exercise only with owner-approved test account, after live DB recovery gates are addressed.

### P5-SEC-02 — Rate limiting and request hardening scope
- Priority: P1. Status: **PARTIAL**.
- Evidence: auth endpoints rate limited (per account + IP); provider-client
  timeouts/deadline and response-cap hardening covered in
  `tests/test_hardening.py`; a documented general API write-path rate-limit
  policy (and its single-replica in-memory limitation) is missing.
- Action: audit remaining write endpoints, document the limitation for the
  single-replica Free-tier topology.

### P5-SEC-03 — Dependency security
- Priority: P1. Status: **PASS** (pip-audit + Bandit + zizmor in every CI run;
  exceptions validated by `scripts/security_exceptions.py`).

### P5-SEC-04 — Logging/secrets/error-handling review
- Priority: P1. Status: **PASS (repository-level)** — PR #129 code/test revision
  `06fd634a448de3b23c4fe5e82ef68c93f605cc8f`, CI Run #631
  (`38261693474`) passed all five jobs.
- Findings corrected: rejected provider URLs are no longer written to warning
  logs; reconciliation failures persist only the exception class rather than
  raw exception text. Deterministic synthetic regressions cover both paths.
- Boundary: no hosted log inspection, live production exception injection,
  provider calls, production database operations, or deployment were performed.
  Hosted security validation remains **NOT VERIFIED**.
- Next: independent human review of PR #129; do not merge without explicit
  authorization.

---

## P6 — Commercial controls and billing

### P6-BILL-01 — Application-side commercial control plane
- Priority: P1. Status: **PASS** (automated tests): entitlements, usage
  ledger, reconciliation, OWNER-only manual mutation, fail-closed production
  configuration.

### P6-BILL-02 — Real payment provider integration
- Priority: P2 for pilot, P0 for commercial production. Status: **BLOCKED**
  (owner approval + provider account + credentials). No paid service will be
  provisioned without explicit approval.

### P6-BILL-03 — Manual pilot commercial model
- Priority: P1. Status: **PASS** (documented in `docs/PILOT_LAUNCH.md`
  section 7): manual agreement/invoice outside the application is acceptable
  for the first pilot, explicitly not represented as in-product payment.

---

## P7 — Deployment, pilot onboarding, and launch operations

### P7-OPS-01 — Hosted readiness verification
- Priority: P0. Status: **PASS** (2026-10-12 external probes `/health` 200,
  `/ready` `{"status":"ready","database":"ok"}` plus Render platform log
  evidence).

### P7-OPS-02 — Pilot onboarding package
- Priority: P1. Status: **PARTIAL**.
- Exists: pilot use case and acceptance criteria
  (`docs/PILOT_LAUNCH.md`), release checklist
  (`docs/RELEASE_CHECKLIST.md`), deployment runbook
  (`docs/PRODUCTION_DEPLOYMENT.md`), backup runbook
  (`docs/DB_BACKUP_RUNBOOK.md`).
- Missing: customer-facing quickstart, sample RFQ + quotation package, example
  report, known-limitations one-pager.
- Autonomy: autonomous (documentation + sample data generation).

### P7-OPS-03 — Incident, support, and feedback triage
- Priority: P1. Status: **PARTIAL** (feedback classification P0–P3 exists in
  `docs/PILOT_LAUNCH.md` section 10; support contact and incident procedure
  need owner input).

### P7-OPS-04 — External monitoring and alerting
- Priority: P1 for pilot. Status: **BLOCKED / NOT VERIFIED** (platform or
  third-party setup; owner decision on tooling).

---

## Critical path to a controlled pilot

1. **P2-BK-02** (autonomous, in progress) — laptop-ready backup tooling.
2. **P2-BK-03 + P2-BK-04** (owner laptop) — live backup and isolated restore
   drill.
3. **P1-DB-01 + P1-DB-02** (owner + change window) — live schema audit, then
   baseline decision.
4. **P1-DB-04** (owner decision before 2026-11-08) — durable database.
5. **P4-AUTH-02** (owner test accounts) — hosted authenticated + isolation
   smoke.
6. **P7-OPS-02** (autonomous) — pilot onboarding package.

Additional gates for commercial production: **P6-BILL-02** (billing provider
verification), **P5-SEC-01/02/04** closure, **P7-OPS-04** monitoring,
**P0-CI-02** workflow decision, and one full pilot feedback cycle
(`docs/PILOT_LAUNCH.md` section 10).
