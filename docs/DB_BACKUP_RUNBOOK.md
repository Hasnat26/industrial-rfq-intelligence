# Database Backup and Recovery Runbook

Owner: operations. Applies to the Render PostgreSQL instance backing
`https://industrial-rfq-intelligence.onrender.com`.

## Constraints

- Render PostgreSQL is on the **Free plan** and **expires 2026-11-08**. It has
  no managed backup or PITR. A logical dump is the only recovery artifact.
- Never store database passwords in this repository, in shell history, or in
  chat. Use session-scoped environment variables or the interactive secure
  prompt built into `scripts/backup_render_db.ps1`.
- Never broaden PostgreSQL inbound rules beyond the existing specific `/32`
  entries. Recheck the current rules in the Render dashboard before each
  backup session; do not modify them without explicit approval.
- Never restore over production. Restore drills target a separate, isolated
  database only.

## Tools and version compatibility

| Where | Tool version | Can dump Render server 16.15? |
|---|---|---|
| Windows laptop | PostgreSQL client 18.6 | Yes (newer client → older server) |
| Linux/macOS with Postgres 16+ | 16+ | Yes |
| Any client older than 16 | <16 | **No** — `pg_dump` must be ≥ the server major version |

Both scripts refuse to run when the client major version is older than the
server and print both versions for the record.

## Backup procedure (Windows laptop)

1. Recheck the Render PostgreSQL **Networking** tab: confirm the `/32` inbound
   rule for the laptop's current external IP. If the IP changed, update the
   `/32` rule in the Render dashboard (never add `0.0.0.0/0`).
2. Open PowerShell and set session-scoped connection variables (values come
   from the Render dashboard's **Connections** panel; never paste them into
   chat):

   ```powershell
   $env:PGHOST   = "<render-db-host>"        # e.g. dpg-xxxxx-a.routedb.render.com
   $env:PGPORT   = "5432"
   $env:PGUSER   = "<render-db-user>"
   $env:PGDATABASE = "<render-db-name>"
   Read-Host -Prompt "Render DB password" -AsSecureString |% {
     $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($_)
     try { $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
     finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
   }
   ```

3. Verify connectivity (must return `PostgreSQL 16.x`):

   ```powershell
   psql -tAc "SELECT version()"
   ```

4. Run the backup with a restore drill into a separate test database you
   create once in the Render dashboard (a second Free PostgreSQL is allowed
   under the free-tier constraint; alternatively use a local PostgreSQL 16+
   instance as the drill target):

   ```powershell
   .\scripts\backup_render_db.ps1 -DatabaseName <render-db-name> `
     -RestoreTest -RestoreTestDatabase <restore-test-db-name>
   ```

5. Record the printed archive path, size, SHA-256, TOC line count, and
   restore-test result. Copy the `.dump`, `.dump.sha256`, and `.dump.toc.txt`
   files to at least two locations (laptop disk + external drive/cloud sync
   of your choice). The `backups/` directory must never be committed.

6. Close the PowerShell session to clear `PGPASSWORD` from the environment.

A POSIX twin (`scripts/backup_render_db.sh`) with the identical command
sequence exists for Git Bash/WSL or Linux hosts.

## Restore-test status

- **Local drill: PASSED 2026-10-11.** The exact command sequence in the
  scripts was executed end to end against a scratch PostgreSQL 14 instance
  populated by this repository's own Alembic chain (`alembic upgrade head`,
  full downgrade to base, and re-upgrade all succeeded on PostgreSQL):
  - `pg_dump --format=custom` archive created (101,320 bytes, SHA-256
    recorded),
  - `pg_restore --list` validated the archive TOC (294 entries),
  - `pg_restore` into a separate isolated database succeeded,
  - all 25 application tables restored; row counts and Alembic head
    (`p8eval001`) verified identical between source and restored databases,
  - the guard that refuses to restore into the source database was verified
    to exit non-zero.
- **Against the live Render database: NOT YET EXECUTED.** The first real
  backup requires the manual steps above with the actual Render credentials.
  Until that archive exists and its restore drill passes, production
  recovery is unverified.

## Recovery procedure (production incident)

1. Prefer **schema-preserving recovery**: provision a new PostgreSQL 16+
   instance, restore the latest archive with the script's command sequence,
   update `INDUSTRIAL_RFQ_DATABASE_URL`, redeploy.
2. Verify `alembic_version` head matches the deployed commit's migration
   chain (`alembic heads` in the repository), then run `/ready`.
3. Do **not** run `alembic downgrade` as part of rollback; schema rollback
   is a separate controlled change (see `docs/PRODUCTION_DEPLOYMENT.md`).
4. Record the archive used, restore duration, and verification results in
   `docs/FINAL_ACCEPTANCE.md`.

## Limitations

- A logical dump is a point-in-time snapshot; transactions committed after
  the dump are not recoverable. Take a dump before every risky migration and
  on a weekly cadence until PITR is available on a paid plan (out of scope
  under the free-tier constraint).
- The archive contains tenant data: store it encrypted and restrict access
  exactly like production credentials.
- Render Free databases expire 2026-11-08; after migration to a new
  database, repeat the backup procedure against the new instance and update
  this runbook.
