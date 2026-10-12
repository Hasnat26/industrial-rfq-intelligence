# Project Continuity Checkpoint

Permanent handover checkpoint for whichever engineer (Freebuff AI or ChatGPT)
is active. Update this file at the end of every meaningful work cycle.

## Resume state (2026-10-12, refreshed after PR #117)

- **Current main commit:** `57b63009e9d61c42d1849124382fe6217eceb983`
- **Latest CI run:** Run #598 (`38214323218`), SUCCESS, all 5 jobs (`postgres-migrations`, `industrial (3.11–3.14)`), including lint, type check, security gate, container smoke, and package smoke —
  <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38214323218>
- **Latest deployed commit (Render):**
  `2a31c006a6e7e3174c6375c6f5226cb3430f373c`
  (deployment `dep-db5s11tckfvc73b8ief0`, live 2026-10-11). No runtime-code
  delta between it and main HEAD (docs/scripts/CI only since).
- **Hosted probes (2026-10-12):** `/health` 200; `/ready` 200
  `{"status":"ready","database":"ok"}`.
- **Active branch / PR:** `docs/continuity-after-pr117-2026-10-12` (this handover refresh; PR to be opened after evidence updates). PRs #116 and #117 are merged; no open PRs were found.
- **Last completed task ID:** P0-CI-01/04, P0-CI-02 (verified FAIL:
  Security+CodeQL workflows `disabled_fork`, cannot enable via App token 403),
  P1-DB-03, P2-BK-01, P4-AUTH-01, P5-SEC-03, P6-BILL-01, P7-OPS-01 (see
  `docs/MARKET_LAUNCH_MASTER_PLAN.md`).
- **Current task ID:** P2-BK-02 (IN PROGRESS) — make the backup/restore
  tooling laptop-ready and independently connected.
- **Exact next action:** on branch `ops/backup-tooling-laptop-ready`, merge
  the preserved local script implementation (tool-directory detection via
  `-PostgresBin`/`$env:PGBIN`/default `C:\Program Files\PostgreSQL\<ver>\bin`
  locations; independent restore connection
  `RestoreHost/RestorePort/RestoreUser` + `$env:RESTORE_PG*`; live server
  identity guard using `port` + `pg_postmaster_start_time()`;
  `-RecreateRestoreDatabase`) with the merged schema-verification logic from
  PRs #114/#115 (columns/views/indexes/constraints/Alembic state + per-table
  row counts + TLS-required), then drill-test every success and refusal path
  against scratch PostgreSQL and update `docs/DB_BACKUP_RUNBOOK.md`.
- **Preserved uncommitted work:** a stash entry `local-backlog-followup` on
  `main` plus copies in `/tmp/preserve/` contain the pre-merge local versions
  of `scripts/backup_render_db.ps1`, `scripts/backup_render_db.sh`,
  `docs/DB_BACKUP_RUNBOOK.md`, `pyproject.toml`, and
  `tests/test_backup_scripts.py`. They predate PRs #114/#115 and must be
  **merged, not restored wholesale** (the merged versions added schema
  verification the local versions lack). Drop the stash only after the merge
  task completes.
- **Latest repository change:** PR #117 merged as `57b63009e9d61c42d1849124382fe6217eceb983`; Run #598 passed. This session verified the merge, branch, and workflow. No live database operations were performed.

## Test and CI evidence

- Local suite (this cycle, pre-docs): full `pytest` green in the workspace
  venv (`/tmp/ffp-venv`), `ruff` + `mypy` clean as of PR #107/#114 merges.
- CI: latest main Run #598 for `57b63009e9d61c42d1849124382fe6217eceb983` passed all five jobs.

## Unresolved risks and owner-controlled dependencies

1. Render Free PostgreSQL expires **2026-11-08**, no managed backup (P1-DB-04).
   Owner must re-check the Render dashboard and approve a durable option.
2. Live database schema baseline is unverified; live DB is IP-allowlisted and
   has reportedly no `alembic_version` table (P1-DB-01/02). Owner laptop
   access required. Never stamp/migrate/reset to resolve uncertainty.
3. Live backup + isolated restore drill (P2-BK-03/04) require owner laptop,
   real credentials (never in chat), and a separate empty target database.
4. Standalone Security and CodeQL workflows remain `disabled_fork`; enabling
   them requires owner GitHub admin (P0-CI-02). Main CI security gate
   (Bandit/pip-audit/zizmor) passes every run.
5. Hosted authenticated + cross-tenant smoke (P4-AUTH-02) needs owner-approved
   test accounts on production.
6. Billing provider integration (P6-BILL-02) needs owner approval and
   provider credentials; the pilot may run on the documented manual model.

## Safe resume instructions for the next AI

1. `git fetch origin && git log origin/main --oneline -5` and compare with the
   main commit above; re-check `gh run list` for newer CI results.
2. Read `docs/MARKET_LAUNCH_MASTER_PLAN.md` for the backlog and
   `docs/LAUNCH_ACCEPTANCE_MATRIX.md` for gate results; do not repeat audits
   that already have PASS evidence unless something changed.
3. If the active task is still P2-BK-02, continue exactly at the "exact next
   action" above. The preserved work lives in the git stash
   `local-backlog-followup` and `/tmp/preserve/` (workspace may not survive;
   if `/tmp/preserve` is gone, reconstruct from the stash or from this
   document's description).
4. Work on a dedicated branch; open a PR; require green CI; merge only when
   checks pass; confirm the commit on `main`; then update this file, the
   acceptance matrix, and the master plan statuses.
5. Never: restore over the source database, run `alembic stamp head` on the
   live DB, widen the DB allowlist, expose credentials in chat, or claim a
   live backup/restore that was not actually executed.

## ChatGPT continuation prompt (ready to copy)

> Continue the Industrial RFQ Intelligence market-launch work from the
> repository checkpoint. First read `docs/PROJECT_CONTINUITY.md`,
> `docs/MARKET_LAUNCH_MASTER_PLAN.md`, and
> `docs/LAUNCH_ACCEPTANCE_MATRIX.md`, then check the latest main commit and
> CI runs on GitHub. Resume the task whose status is IN PROGRESS in the
> continuity file (currently P2-BK-03/P2-BK-04: owner-operated live backup and isolated
> restore drill after PR #117's laptop-ready tooling was merged. If owner access
> is not available, proceed with autonomous P5-SEC-01 adversarial regression tests.
> Do not repeat completed audits. Follow the safety prohibitions in the
> continuity file. Commit on a dedicated branch, open a PR, wait for green
> CI, merge, confirm on main, and update the three control documents before
> starting the next task.
