# Database Backup and Recovery Runbook

Owner: operations. Applies to the Render PostgreSQL instance backing
`https://industrial-rfq-intelligence.onrender.com`.

## Constraints

- Render PostgreSQL is on the **Free plan** and **expires 2026-11-08**. It has
  no managed backup or PITR. A logical dump is the only recovery artifact.
  Re-check the Render dashboard before acting on this date.
- Never store passwords in source control, shell history, or chat.
- Keep inbound database access restricted to explicit, current `/32` entries.
  Never add `0.0.0.0/0` to make a connector work.
- Never restore over the source/production database. Restore drills require a
  separate pre-created, empty target database on an independent connection.
- Live Render backup and restore remain **NOT VERIFIED** until performed using
  the owner's actual credentials and recorded here with evidence.

## Tools and version compatibility

Use PostgreSQL client tools whose major version is at least the server's
(server is 16.x; the owner's laptop has 18.6, which is valid: client 18 can
dump a 16 server). The restore server must be at least as new as the source
server.

Both scripts locate the tools **without any PATH change**:

- PowerShell: `-PostgresBin` parameter, then `$env:PGBIN`, then the default
  install locations `C:\Program Files\PostgreSQL\18\bin` down to `14\bin`
  (first one found), then PATH as a last resort. Typical laptop invocation:
  `.\scripts\backup_render_db.ps1 -PostgresBin "C:\Program Files\PostgreSQL\18\bin" ...`
- POSIX: `PG_BIN` environment variable (or the first positional argument),
  then PATH as a last resort, e.g. `PG_BIN=/usr/lib/postgresql/16/bin`.

## Client and TLS requirements

The **source** connection requires TLS through libpq's `PGSSLMODE` setting
(default `verify-full`). Use the hostname from Render's connection
information so certificate hostname validation can succeed. Do not disable
TLS to bypass connection errors.

The **restore-drill** connection is separately configurable and typically
targets a local database: `RESTORE_PGSSLMODE` controls its TLS mode
(defaults to the source mode when the drill points at the same endpoint,
otherwise `prefer` so a local drill server without TLS still works).

## Windows PowerShell

1. Confirm the laptop's current IP is already allowed by a specific `/32`
   rule. If not, stop and follow the owner's approved network-change process.
2. Set session-only environment variables from Render Connections; never paste
   values into chat or commit them:

   ```powershell
   $env:PGHOST = "<render-db-host>"
   $env:PGPORT = "5432"
   $env:PGUSER = "<render-db-user>"
   $env:PGDATABASE = "<render-db-name>"
   $env:PGSSLMODE = "verify-full"
   $secure = Read-Host -Prompt "Render DB password" -AsSecureString
   $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
   try { $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
   finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
   ```

3. Check connectivity without exposing secrets (adjust the path to the
   installed tools):

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql" -X -v ON_ERROR_STOP=1 -tAc "SHOW server_version"
   ```

4. Pause application writes for the duration of the comparison so live row
   counts represent the same quiesced state as the backup. Then run the backup
   with an isolated restore drill against a **separate, pre-created, empty**
   database on the local drill server (password via
   `$env:RESTORE_PGPASSWORD` or a secure prompt):

   ```powershell
   .\scripts\backup_render_db.ps1 -PostgresBin "C:\Program Files\PostgreSQL\18\bin" `
       -RestoreTest -RestoreTestDatabase ffp_restore_test `
       -RestoreHost 127.0.0.1 -RestorePort 5432 -RestoreUser postgres `
       -RecreateRestoreDatabase
   ```

   `-RecreateRestoreDatabase` drops and recreates the drill database first
   (the drill user then needs CREATEDB rights on the local drill server).
   The script refuses to run the drill if the target is the same server and
   database as the source — verified from the live server identity
   (`port` + `pg_postmaster_start_time()`), which also catches the source
   reached through a second interface or alias such as `localhost` vs
   `127.0.0.1`.
5. Preserve the dump, SHA-256 and TOC artifacts in two protected locations.
   Backups contain tenant data and must be encrypted with restricted access.
   Close the session when finished.

## POSIX

Set `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGPASSWORD`, and
`PGSSLMODE=verify-full` in the current shell. Pause application writes during
the restore comparison. Run `./scripts/backup_render_db.sh` (optionally with
`PG_BIN=/path/to/bin`). For a restore drill, additionally set
`RESTORE_TEST_DATABASE` plus independent `RESTORE_PGHOST`/`RESTORE_PGPORT`/
`RESTORE_PGUSER`/`RESTORE_PGPASSWORD` (and `RECREATE_RESTORE_DATABASE=1` to
drop/recreate the drill database first). The drill target is checked against
the live source server identity (`port` + `pg_postmaster_start_time()`) and
the drill is refused if it is the same server and database as the source.

## Verification semantics

Both scripts create a temporary custom-format dump, validate its TOC with
`pg_restore --exit-on-error` semantics, publish the archive only after TOC
validation, and record a SHA-256 checksum. For a restore drill they compare
table inventories and column definitions, view definitions, index
definitions, constraints, and Alembic revision state (including whether the
Alembic table exists), then compare row counts for every ordinary table.
Client and restore-server major versions are checked against the source
server version before anything runs.

Matching schema metadata and row counts are useful operational checks, not a
cryptographic proof that every row value is identical. Because the source is
queried after the dump is created, writes must be paused for the comparison or
row-count differences may reflect legitimate concurrent changes. Stronger
assurance requires table-level content checksums or application invariants on
an isolated consistent snapshot. These scripts do not claim a live restore has
passed until actually executed.

## Scratch-test evidence (2026-10-12)

Both script variants were drill-tested against scratch PostgreSQL instances,
covering: successful dump → TOC validation → SHA-256 → isolated restore with
schema/row-count verification; tool-directory detection without PATH changes;
independent restore connections; refusal paths (same database as source, same
server+database detected via live identity even through a different interface
alias, system database targets, invalid names, older restore server, missing
tools); and cleanup of incomplete dumps. This establishes the tooling is
correct, **not** that the live Render database has been backed up.

## Recovery

Restore the latest verified archive into a separately provisioned compatible
PostgreSQL instance. Verify the Alembic head against the target release, then
update protected configuration and redeploy. Never automate a downgrade as
rollback, and never reset or overwrite the source.

**BLOCKED owner operation:** run the live dump/restore with actual
credentials, the existing restricted allowlist, and a separate restore target.
Do not enable paid infrastructure without explicit approval.
