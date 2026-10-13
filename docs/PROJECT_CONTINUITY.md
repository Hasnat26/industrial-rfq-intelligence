# Project Continuity Checkpoint

Permanent handover checkpoint for whichever engineer (Freebuff AI or ChatGPT)
is active. Update this file at the end of every meaningful work cycle.

## Resume state (2026-10-13, T6 pilot end-to-end acceptance)

- **Current main commit:** `f363adc562a494de57cca58c530c99afdfba2818`
- **Current main CI:** Run `38288890112` SUCCESS for `f363adc562a494de57cca58c530c99afdfba2818` (merge of PR #129) — <https://github.com/Hasnat26/industrial-rfq-intelligence/actions/runs/38288890112>.
- **PR #122 validation:** Run #611 (`38219287584`) SUCCESS for PR head `4e3e0420a815c9c3eec0e662f6be24e05e231925`; merged as `656781d2f4761d4a77a43ee93be74d671f6a0b61`.

- **Latest deployed commit (Render):**
  `2a31c006a6e7e3174c6375c6f5226cb3430f373c`
  (deployment `dep-db5s11tckfvc73b8ief0`, live 2026-10-11). PR #122 adds a runtime-code delta in `src/freellmpool/industrial.py` (prompt boundary and extraction-size limits). It is merged to main but is not yet shown as deployed; the latest confirmed Render deployment remains `2a31c006a6e7e3174c6375c6f5226cb3430f373c`.
- **Hosted probes (2026-10-12):** `/health` 200; `/ready` 200
  `{"status":"ready","database":"ok"}`.
- **Open PRs verified 2026-10-13:** #124 (docs/runtime state), #128
  (synthetic pilot source), #130 (pilot onboarding), #131 (hosted acceptance
  plan), #132 (Render recovery), and **#133** (`fix/t24-r30-review-accounting-markdown`,
  head `178ffae710a06763ca4db824e9665bb6c7122ab4`, MERGEABLE, latest CI green).
  PR #129 merged as `f363adc562a494de57cca58c530c99afdfba2818`. None of the
  open PRs were modified, approved, or merged this cycle; merges remain
  owner-authorized only.

- **Previously completed task IDs:** P0-CI-01/04, P0-CI-02 (standalone security workflows remain owner-dependent), P1-DB-03, P2-BK-01, P4-AUTH-01, P5-SEC-03, P5-SEC-04 (repository-level fix and regression coverage CI-verified; hosted validation NOT VERIFIED), P6-BILL-01, P7-OPS-01.
- **Previously completed task ID:** T24-R9 — PR #129 reconciliation
  exception-boundary hardening (merged as `f363adc562a494de57cca58c530c99afdfba2818`).
- **Last completed task ID:** **T6 — end-to-end pilot acceptance**, on branch
  `story/t6-pilot-end-to-end-acceptance` (based on `f363adc5...`, local commit
  only; not pushed). Delivers `tests/test_pilot_end_to_end.py` (wired into
  `pyproject.toml` testpaths) and a genuine defect fix in
  `src/freellmpool/api/app.py`: `POST /offers/{id}/technical-resubmission` now
  carries `price`/`currency`/`lead_time`/`warranty` onto the revision offer.
  Before the fix, any technical resubmission silently dropped the vendor's
  commercial terms from every commercial view (no endpoint can re-enter them),
  so a clarified vendor had no price at commercial comparison. T1-T5 were
  reconciled against source and tests this cycle and are DONE (no code change).
- **Exact next action:** push `story/t6-pilot-end-to-end-acceptance`, open a
  PR, wait for green CI, and hand merge approval to the owner (do not merge
  without explicit authorization). Keep PR #133 separate and unmerged; T6 does
  not touch its files (`src/freellmpool/industrial.py`,
  `industrial_report.py`, `tests/test_industrial_demo.py`,
  `tests/test_t24_r30_reporting_regressions.py`); the only shared file is
  `pyproject.toml`, where T6 appends to the end of `testpaths` while PR #133
  inserts near the top, so the two edits merge cleanly. Continue to treat live
  backup/restore (P2-BK-03/04), live schema baseline/expiry (P1-DB-01/04),
  hosted authenticated tenant-isolation smoke (P4-AUTH-02), and hosted
  logging/error validation as owner-dependent or NOT VERIFIED until executed
  with approved access.

- **Preserved uncommitted work:** a stash entry `local-backlog-followup` on
  `main` plus copies in `/tmp/preserve/` contain the pre-merge local versions
  of `scripts/backup_render_db.ps1`, `scripts/backup_render_db.sh`,
  `docs/DB_BACKUP_RUNBOOK.md`, `pyproject.toml`, and
  `tests/test_backup_scripts.py`. They predate PRs #114/#115 and must be
  **merged, not restored wholesale** (the merged versions added schema
  verification the local versions lack). Drop the stash only after the merge
  task completes.
- **Latest repository change:** main is `f363adc562a494de57cca58c530c99afdfba2818`
  (PR #129 merge) with CI Run `38288890112` green. T6 is committed locally on
  `story/t6-pilot-end-to-end-acceptance` and awaits push/PR/CI. PRs #124,
  #128, #130, #131, #132, and #133 remain open/unmerged and untouched. No
  production database operations or deployments were performed.

## Test and CI evidence

- **T6 local verification (2026-10-13, workspace venv `/tmp/ffp-venv`, branch
  `story/t6-pilot-end-to-end-acceptance` on top of `f363adc5...`):**
  `pytest` → **281 passed in 66.84s** (bare `pytest` uses the `testpaths`
  list, which now includes `tests/test_pilot_end_to_end.py`);
  `ruff check .` → All checks passed;
  `mypy src/freellmpool/api src/freellmpool/procurement_domain.py` →
  Success, no issues in 17 files. No CI run exists for this branch because it
  has not been pushed yet.
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

> Continue the Industrial RFQ Intelligence delivery work from the repository
> checkpoint. Verify the current main SHA, latest main CI, open PRs, and exact
> PR heads before acting. Main is `f363adc562a494de57cca58c530c99afdfba2818`
> with CI green. Stories T1-T5 (clarification read schema, clarification
> lifecycle, revised offers/RFQ revisions, technical qualification gate,
> commercial normalization) are reconciled as DONE against source and tests.
> T6 (end-to-end pilot acceptance) is complete on branch
> `story/t6-pilot-end-to-end-acceptance`: new `tests/test_pilot_end_to_end.py`
> plus the resubmission commercial-field preservation fix in
> `src/freellmpool/api/app.py`; local `pytest` 281 passed, `ruff` and `mypy`
> clean; the branch is not pushed. Push it, open a PR, wait for green CI, and
> let the owner merge. PR #133
> (`fix/t24-r30-review-accounting-markdown`, head `178ffae710a06763ca4db824e9665bb6c7122ab4`)
> and PRs #124/#128/#130/#131/#132 remain open/unmerged; do not count their
> content as delivered, and do not merge any PR without explicit
> authorization. Do not claim hosted logging/error handling, live backup/
> restore, live database schema baseline, or hosted tenant-isolation tests
> passed without their own execution evidence. Preserve all owner-controlled
> safety constraints in this file.
