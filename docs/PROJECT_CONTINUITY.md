# Project Continuity Checkpoint

Permanent handover checkpoint for whichever engineer (Freebuff AI or ChatGPT)
is active. Update this file at the end of every meaningful work cycle.

## Resume state (2026-10-12, refreshed after PR #120)

- **Current main commit:** `656781d2f4761d4a77a43ee93be74d671f6a0b61`
- **Latest verified main CI run before PR #122:** Run #609 (`38218450625`), SUCCESS for `39b749496ac9e7c518ebf904af8ead979971f756` — <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38218450625>.
- **PR #122 validation:** Run #611 (`38219287584`), SUCCESS for `4e3e0420a815c9c3eec0e662f6be24e05e231925`; PR #122 merged as `656781d2f4761d4a77a43ee93be74d671f6a0b61`. Main CI for the merge commit must still complete.

- **Latest deployed commit (Render):**
  `2a31c006a6e7e3174c6375c6f5226cb3430f373c`
  (deployment `dep-db5s11tckfvc73b8ief0`, live 2026-10-11). No runtime-code
  delta between it and main HEAD (docs/scripts/CI only since).
- **Hosted probes (2026-10-12):** `/health` 200; `/ready` 200
  `{"status":"ready","database":"ok"}`.
- **Active branch / PR:** PR #122 merged. Main now includes prompt-injection boundary and extraction size-limit hardening.

- **Last completed task ID:** P0-CI-01/04, P0-CI-02 (verified FAIL:
  Security+CodeQL workflows `disabled_fork`, cannot enable via App token 403),
  P1-DB-03, P2-BK-01, P4-AUTH-01, P5-SEC-03, P6-BILL-01, P7-OPS-01 (see
  `docs/MARKET_LAUNCH_MASTER_PLAN.md`).
- **Last completed task ID:** P5-SEC-01 code and regression coverage merged (PR #122; CI Run #611 passed all five jobs). This is repository/test evidence; no live hosted prompt-injection exercise was run.
- **Exact next action:** monitor main CI for merge commit, then continue P5-SEC-04 logging/secrets/error-handling review using source inspection and synthetic tests. Keep live backup/restore (P2-BK-03/04), database schema baseline/expiry (P1-DB-01/04), and hosted authenticated tenant-isolation smoke (P4-AUTH-02) in blocked/unverified states until owner-controlled operations are safely executed.

- **Preserved uncommitted work:** a stash entry `local-backlog-followup` on
  `main` plus copies in `/tmp/preserve/` contain the pre-merge local versions
  of `scripts/backup_render_db.ps1`, `scripts/backup_render_db.sh`,
  `docs/DB_BACKUP_RUNBOOK.md`, `pyproject.toml`, and
  `tests/test_backup_scripts.py`. They predate PRs #114/#115 and must be
  **merged, not restored wholesale** (the merged versions added schema
  verification the local versions lack). Drop the stash only after the merge
  task completes.
- **Latest repository change:** PR #122 merged as `656781d2f4761d4a77a43ee93be74d671f6a0b61`. Run #611 passed on its PR head `4e3e0420a815c9c3eec0e662f6be24e05e231925`; main merge-commit CI is the next required check. No live database operations were performed.

## Test and CI evidence

- Local suite (this cycle, pre-docs): full `pytest` green in the workspace
  venv (`/tmp/ffp-venv`), `ruff` + `mypy` clean as of PR #107/#114 merges.
- Main CI Run #609 passed for `39b749496ac9e7c518ebf904af8ead979971f756`. PR CI Run #611 passed all five jobs on `4e3e0420a815c9c3eec0e662f6be24e05e231925`. Main CI for the merge commit is pending at this checkpoint.

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
