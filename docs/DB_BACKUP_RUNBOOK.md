# Database Backup and Recovery Runbook

Owner: operations. Applies to the Render PostgreSQL instance backing Industrial
RFQ Intelligence.

## Constraints

- The recorded Render Free PostgreSQL instance expires on **2026-11-08** and
  has no managed backup or PITR; re-check current service state before acting.
- Never store passwords in source control, shell history, or chat.
- Keep inbound database access restricted to explicit, current `/32` entries.
  Never add `0.0.0.0/0` to make a connector work.
- Never restore over the source/production database. Restore drills require a
  separate pre-created, empty target database.
- Live Render backup and restore remain **NOT VERIFIED** until performed using
  the owner's actual credentials.

## Client and TLS requirements

Use PostgreSQL client tools whose major version is at least the server's.
Both scripts require TLS through libpq's `PGSSLMODE` setting (default
`verify-full`). Use the hostname from Render's connection information so
certificate hostname validation can succeed. Do not disable TLS to bypass
connection errors.

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

3. Check connectivity without exposing secrets:
   ```powershell
   psql -X -v ON_ERROR_STOP=1 -tAc "SHOW server_version"
   ```
4. Create a separate, empty restore-test database first. Pause application writes
   for the duration of the comparison so live row counts represent the same
   quiesced state as the backup. Then run:
   ```powershell
   .\scripts\backup_render_db.ps1 -DatabaseName <source-db-name> -RestoreTest -RestoreTestDatabase <separate-restore-db-name>
   ```
5. Preserve the dump, SHA-256 and TOC artifacts in two protected locations.
   Backups contain tenant data and must be encrypted with restricted access.
   Close the session when finished.

## POSIX

Set `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGPASSWORD`, and
preferably `PGSSLMODE=verify-full` in the current shell. Pause application writes
during the restore comparison. Run `./scripts/backup_render_db.sh`. For a restore
drill, set `RESTORE_TEST_DATABASE` to a separate pre-created database name.

## Verification semantics

Scripts create a temporary custom-format dump, validate its TOC, publish the
archive only after TOC validation, and record a SHA-256 checksum. For a restore
drill they use pg_restore error-stop behavior, compare table inventories and
column definitions, view definitions, index definitions, constraints, and
Alembic revision state (including whether the Alembic table exists), then
compare row counts for every ordinary table.

Matching schema metadata and row counts are useful operational checks, not a
cryptographic proof that every row value is identical. Because the source is
queried after the dump is created, writes must be paused for the comparison or
row-count differences may reflect legitimate concurrent changes. Stronger
assurance requires table-level content checksums or application invariants on
an isolated consistent snapshot. These scripts do not claim a live restore has
passed until actually executed.

## Historical scratch evidence

A previous repository run reported a successful basic dump/list/restore
against scratch PostgreSQL. This does not establish live Render recovery. The
structural-verification implementation must pass CI before it is treated as
current evidence.

## Recovery

Restore the latest verified archive into a separately provisioned compatible
PostgreSQL instance. Verify the Alembic head against the target release, then
update protected configuration and redeploy. Never automate a downgrade as
rollback, and never reset or overwrite the source.

**BLOCKED owner operation:** run the live dump/restore with actual credentials,
the existing restricted allowlist, and a separate restore target. Do not enable
paid infrastructure without explicit approval.
