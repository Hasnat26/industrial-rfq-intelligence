# Project Continuity Checkpoint

Permanent handover checkpoint for whichever engineer (Freebuff AI or ChatGPT)
is active. Update this file at the end of every meaningful work cycle.

## Resume state (2026-10-12, PR #129 exception-boundary hardening)

- **Current main commit:** `fe44588116f6d1afb0a7c70a0a3b661ec3db6593`
- **Current main CI:** Run #624 (`38237349041`) SUCCESS for `fe44588116f6d1afb0a7c70a0a3b661ec3db6593` — <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38237349041>.
- **PR #122 validation:** Run #611 (`38219287584`) SUCCESS for PR head `4e3e0420a815c9c3eec0e662f6be24e05e231925`; merged as `656781d2f4761d4a77a43ee93be74d671f6a0b61`.

- **Latest deployed commit (Render):**
  `2a31c006a6e7e3174c6375c6f5226cb3430f373c`
  (deployment `dep-db5s11tckfvc73b8ief0`, live 2026-10-11). PR #122 adds a runtime-code delta in `src/freellmpool/industrial.py` (prompt boundary and extraction-size limits). It is merged to main but is not yet shown as deployed; the latest confirmed Render deployment remains `2a31c006a6e7e3174c6375c6f5226cb3430f373c`.
- **Hosted probes (2026-10-12):** `/health` 200; `/ready` 200
  `{"status":"ready","database":"ok"}`.
- **Open PRs verified this cycle:** PR #128 remains open/unmerged at head `fe72dffcd54343530da229c26d0beb7b92ae78e8`; PR #129 remains open/unmerged, with reconciliation exception-boundary hardening and regression tests in code/test commit `179257b9777285b11f1ede73b27beef0df710793`; PR #130 remains open/unmerged at head `d9e3bd3223a75b5869a688807530af45a583092f`; PR #131 remains open/unmerged at head `aac1fb1e79d5fa0ec56e58e3b79e825e5f8a42c2`. PR #124 also appears open in GitHub; it was not modified. PRs #128, #130, and #131 were not modified, merged, or deployed.

- **Previously completed task IDs:** P0-CI-01/04, P0-CI-02 (standalone security workflows remain owner-dependent), P1-DB-03, P2-BK-01, P4-AUTH-01, P5-SEC-03, P5-SEC-04 (repository-level fix and regression coverage CI-verified; hosted validation NOT VERIFIED), P6-BILL-01, P7-OPS-01.
- **Last completed task ID:** T24-R9 — PR #129 reconciliation exception-boundary hardening. PR #129 code/test revision `179257b9777285b11f1ede73b27beef0df710793` passed CI Run #648 (`38277498580`), all five jobs. This is repository-level evidence only; hosted logs and live runtime failure behavior were not tested.
- **Exact next action:** obtain independent human review for PR #129; do not merge without explicit authorization. Keep PR #128 separate and unmerged. Continue to treat live backup/restore (P2-BK-03/04), live schema baseline/expiry (P1-DB-01/04), hosted authenticated tenant-isolation smoke (P4-AUTH-02), and hosted logging/error validation as owner-dependent or NOT VERIFIED until executed with approved access.

- **Preserved uncommitted work:** a stash entry `local-backlog-followup` on
  `main` plus copies in `/tmp/preserve/` contain the pre-merge local versions
  of `scripts/backup_render_db.ps1`, `scripts/backup_render_db.sh`,
  `docs/DB_BACKUP_RUNBOOK.md`, `pyproject.toml`, and
  `tests/test_backup_scripts.py`. They predate PRs #114/#115 and must be
  **merged, not restored wholesale** (the merged versions added schema
  verification the local versions lack). Drop the stash only after the merge
  task completes.
- **Latest repository change:** main remains `fe44588116f6d1afb0a7c70a0a3b661ec3db6593` with Run #624 green. PR #129 code/test commit `179257b9777285b11f1ede73b27beef0df710793` passed Run #648 (`38277498580`), all five jobs. The current PR #129 head and latest exact-head CI result are tracked in the [live pull request](https://github.com/Hasnat26/industrial-rfq-intelligence/pull/129) and [GitHub Actions history](https://github.com/Hasnat26/industrial-rfq-intelligence/actions?query=branch%3Asecurity%2Fp5-sec-04-sanitize-reconciliation-errors). The validated code/test revision is `179257b9777285b11f1ede73b27beef0df710793`, which passed Run #648 (`38277498580`), all five jobs. Independent human review remains pending; hosted security acceptance remains NOT VERIFIED. PRs #128, #130, and #131 remain open/unmerged and untouched. No production database operations or deployments were performed.

## Test and CI evidence

- No local repository shell/test runner was available for T24-R9; GitHub Actions is the execution evidence.
- Main CI Run #624 passed on `fe44588116f6d1afb0a7c70a0a3b661ec3db6593`.
- PR #129 code/test Run #648 (`38277498580`) passed all five jobs on `179257b9777285b11f1ede73b27beef0df710793`. For the current PR head and its exact-head CI result, use the [live PR](https://github.com/Hasnat26/industrial-rfq-intelligence/pull/129) and [Actions history](https://github.com/Hasnat26/industrial-rfq-intelligence/actions?query=branch%3Asecurity%2Fp5-sec-04-sanitize-reconciliation-errors). This is repository-level evidence only; hosted security acceptance remains NOT VERIFIED.

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

> Continue the Industrial RFQ Intelligence launch work from the repository
> checkpoint. Verify the current main SHA, latest main CI, open PRs, and exact
> PR heads before acting. PR #128 is the synthetic source-document pilot and
> remains open/unmerged. PR #129 contains the P5-SEC-04 exception-boundary
> hardening and focused failure-path tests; code/test commit `179257b9777285b11f1ede73b27beef0df710793`
> passed CI Run #648. The current PR #129 head and latest exact-head CI result are available in the [live PR](https://github.com/Hasnat26/industrial-rfq-intelligence/pull/129) and [Actions history](https://github.com/Hasnat26/industrial-rfq-intelligence/actions?query=branch%3Asecurity%2Fp5-sec-04-sanitize-reconciliation-errors). Independent human review remains pending and hosted security acceptance remains NOT VERIFIED. PRs #128, #130, and #131 remain
> open/unmerged; do not count their content as delivered or deployed. Do not
> merge any PR without explicit authorization. Do not claim hosted logging/error handling, live backup/
> restore, live database schema baseline, or hosted tenant-isolation tests
> passed without their own execution evidence. Preserve all owner-controlled
> safety constraints in this file.
