<#
.SYNOPSIS
    Logical backup, archive validation, and optional isolated restore drill
    for the Industrial RFQ Intelligence Render PostgreSQL database.

.DESCRIPTION
    Creates a timestamped custom-format pg_dump archive, validates it with
    pg_restore --list, records a SHA-256 checksum, and (optionally) performs
    a restore drill into a SEPARATE test database with an INDEPENDENT
    connection (host, port, user, database, password may all differ from the
    source). A restore into the source database is refused twice: from the
    configured connection parameters and from the live server identity
    reported by each connection (port + pg_postmaster_start_time), which
    catches the same server/database reached through a different interface or
    alias (127.0.0.1 vs localhost vs IPv6 loopback vs DNS names).

    PostgreSQL tools are located WITHOUT any PATH change:
      1. -PostgresBin parameter,
      2. $env:PGBIN,
      3. the default install locations
         "C:\Program Files\PostgreSQL\<18..14>\bin" (first one found),
      4. PATH as a last resort.

    The SOURCE connection must use TLS: $env:PGSSLMODE defaults to
    "verify-full" and must be one of verify-full / verify-ca / require. The
    drill connection uses $env:RESTORE_PGSSLMODE when set, inherits the
    source mode when pointing at the same endpoint, and otherwise defaults to
    "prefer" so a local drill server without TLS still works.

    Credentials are never accepted as command-line arguments (argv is visible
    in process listings). The source password is read once via a secure
    prompt into the session environment only when PGPASSWORD is not already
    set; the restore password comes from $env:RESTORE_PGPASSWORD, or is
    reused from the source, or is prompted separately when the restore
    host/port/user differ. This script never prints secret values.

    A failed or interrupted dump never produces a file with the final
    *.dump name: pg_dump writes to *.dump.part, and the archive is renamed
    only after pg_restore --list validates it.

    Restore drills compare table/column inventories, view/index/constraint
    definitions, Alembic revision state, and per-table row counts before
    reporting PASSED.

.EXAMPLE
    .\scripts\backup_render_db.ps1 -PostgresBin "C:\Program Files\PostgreSQL\18\bin" `
        -DatabaseHost dpg-xxxxx-a.routedb.render.com -DatabaseUser industrial_rfq_user `
        -DatabaseName industrial_rfq -RestoreTest -RestoreTestDatabase ffp_restore_test `
        -RestoreHost 127.0.0.1 -RestorePort 5432 -RestoreUser postgres `
        -RecreateRestoreDatabase
    # Source = Render production; drill target = a LOCAL PostgreSQL test
    # database that is dropped and recreated first. Passwords come from
    # $env:PGPASSWORD / $env:RESTORE_PGPASSWORD or secure prompts.

.NOTES
    pg_dump must be the SAME OR NEWER major version than the source server
    (client 18.x can dump a 16.x server; the reverse is not supported). The
    restore server must be at least as new as the source server.
    The restore drill requires a restore user that can connect to the drill
    database; with -RecreateRestoreDatabase it must also be able to create
    and drop databases (typically a superuser on the LOCAL drill server).
#>
[CmdletBinding()]
param(
    # PostgreSQL tools directory (no PATH change required).
    [Parameter(Mandatory = $false)] [string]$PostgresBin = $env:PGBIN,

    # Source (production) connection.
    [Parameter(Mandatory = $false)] [string]$DatabaseHost = $env:PGHOST,
    [Parameter(Mandatory = $false)] [int]$DatabasePort = 5432,
    [Parameter(Mandatory = $false)] [string]$DatabaseUser = $env:PGUSER,
    [Parameter(Mandatory = $false)] [string]$DatabaseName = $env:PGDATABASE,

    [Parameter(Mandatory = $false)] [string]$OutputDirectory = (Join-Path (Get-Location) "backups"),

    # Restore-drill connection: fully independent from the source.
    [Parameter(Mandatory = $false)] [switch]$RestoreTest,
    [Parameter(Mandatory = $false)] [string]$RestoreTestDatabase = $env:RESTORE_TEST_DATABASE,
    [Parameter(Mandatory = $false)] [string]$RestoreHost = $env:RESTORE_PGHOST,
    [Parameter(Mandatory = $false)] [int]$RestorePort = 5432,
    [Parameter(Mandatory = $false)] [string]$RestoreUser = $env:RESTORE_PGUSER,
    # Drop and recreate the drill database before restoring (drill target only).
    [Parameter(Mandatory = $false)] [switch]$RecreateRestoreDatabase
)

$ErrorActionPreference = "Stop"

function Convert-SecureToPlain {
    param([System.Security.SecureString]$Secure)
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Invoke-Psql {
    # Run psql with explicit credentials, never leaking them to argv.
    param([string[]]$Arguments, [string]$Password)
    $env:PGPASSWORD = $Password
    try {
        $output = @(& $psql -X -v ON_ERROR_STOP=1 @Arguments)
        if ($LASTEXITCODE -ne 0) { return $null }
        return (($output | Select-Object -First 1) -as [string])
    }
    finally {
        $env:PGPASSWORD = $sourcePw
    }
}

foreach ($name in @("DatabaseHost", "DatabaseUser", "DatabaseName")) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $name -ValueOnly))) {
        throw "$name is required (parameter or matching PG* environment variable)."
    }
}

# ---- Locate PostgreSQL tools (no PATH modification required) --------------
$explicitBin = -not [string]::IsNullOrWhiteSpace($PostgresBin)
if ($explicitBin) {
    $candidateDirs = @($PostgresBin)
}
else {
    $candidateDirs = @(
        18..14 | ForEach-Object { "C:\Program Files\PostgreSQL\$_\bin" }
    )
}
$binDir = $null
foreach ($dir in $candidateDirs) {
    if (Test-Path (Join-Path $dir "pg_dump") -PathType Leaf) { $binDir = $dir; break }
}
if (-not $binDir -and $explicitBin) {
    # An explicitly requested tools directory that lacks pg_dump is an error;
    # silently switching to PATH would hide a misconfigured invocation.
    throw "PostgreSQL tools were not found in the requested directory '$PostgresBin'."
}
if (-not $binDir) {
    foreach ($tool in @("pg_dump", "pg_restore", "psql", "dropdb", "createdb")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "$tool was not found. Pass -PostgresBin `"C:\Program Files\PostgreSQL\18\bin`" (no PATH change needed). Probed: $($candidateDirs -join ', ') and PATH."
        }
    }
    $binDir = ""  # resolve tools from PATH
}
$resolve = { param($tool) if ($binDir) { Join-Path $binDir $tool } else { (Get-Command $tool).Source } }
$pgDump = & $resolve "pg_dump"
$pgRestore = & $resolve "pg_restore"
$psql = & $resolve "psql"
foreach ($pair in @(@("pg_dump", $pgDump), @("pg_restore", $pgRestore), @("psql", $psql))) {
    if (-not $pair[1] -or -not (Test-Path $pair[1] -PathType Leaf)) {
        throw "$($pair[0]) was not found at '$($pair[1])'."
    }
}
Write-Host "PostgreSQL tools: $(if ($binDir) { $binDir } else { '(PATH)' })"

# ---- Source credentials and TLS -------------------------------------------
if ([string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
    $secure = Read-Host -AsSecureString "PostgreSQL password for $DatabaseUser (source)"
    $env:PGPASSWORD = Convert-SecureToPlain $secure
}

$env:PGHOST = $DatabaseHost
$env:PGPORT = "$DatabasePort"
$env:PGUSER = $DatabaseUser
$env:PGDATABASE = $DatabaseName
if ([string]::IsNullOrWhiteSpace($env:PGSSLMODE)) { $env:PGSSLMODE = "verify-full" }
if ($env:PGSSLMODE -notin @("verify-full", "verify-ca", "require")) {
    throw "PGSSLMODE must require TLS."
}
$sourcePw = $env:PGPASSWORD
$sourceSslMode = $env:PGSSLMODE

$toolVersion = ([string](& $pgDump --version)).Trim()
if ($LASTEXITCODE -ne 0) { throw "pg_dump --version failed" }
$serverVersion = (Invoke-Psql @("-tAc", "SHOW server_version") $env:PGPASSWORD)
if ($null -eq $serverVersion) { throw "could not connect to the source database" }
$serverVersion = $serverVersion.Trim()
$toolMajor = [int](($toolVersion -split "pg_dump \(PostgreSQL\) ")[1].Split(".")[0])
$serverMajor = [int](($serverVersion -split "\.")[0])
Write-Host "pg_dump: $toolVersion"
Write-Host "source  : PostgreSQL $serverVersion (${DatabaseHost}:${DatabasePort}/$DatabaseName, ssl=$($env:PGSSLMODE))"
if ($toolMajor -lt $serverMajor) {
    throw "pg_dump major version ($toolMajor) is older than the source server ($serverMajor). Upgrade the client tools; downgrading a dump is not supported."
}

# ---- Restore-drill guards (BEFORE any dump or destructive action) ---------
$restoreVerified = "not requested"
$restorePassword = $null
if ($RestoreTest) {
    if ([string]::IsNullOrWhiteSpace($RestoreTestDatabase)) {
        throw "-RestoreTest requires -RestoreTestDatabase naming a SEPARATE database."
    }
    if ($RestoreTestDatabase -notmatch '^[A-Za-z_][A-Za-z0-9_]{0,62}$') {
        throw "Invalid restore database name '$RestoreTestDatabase'."
    }
    if ($RestoreTestDatabase -in @("postgres", "template0", "template1")) {
        throw "Refusing to use system database '$RestoreTestDatabase' as the restore target."
    }
    if ([string]::IsNullOrWhiteSpace($RestoreHost)) { $RestoreHost = $DatabaseHost }
    if ([string]::IsNullOrWhiteSpace($RestoreUser)) { $RestoreUser = $DatabaseUser }
    if ($RestorePort -eq 5432 -and $env:RESTORE_PGPORT) { $RestorePort = [int]$env:RESTORE_PGPORT }

    $sameEndpoint = ($RestoreHost -ieq $DatabaseHost) -and ($RestorePort -eq $DatabasePort)
    if ($RestoreTestDatabase -eq $DatabaseName) {
        # Same database name as the source: only acceptable when the drill
        # endpoint is provably a different server (verified live below).
        if ($sameEndpoint) {
            throw "Refusing to restore into the source database '$DatabaseName'. Use a separate restore-test database with an independent connection."
        }
    }

    # Drill TLS: explicit override, else inherit when same endpoint, else
    # prefer (a local drill server usually has no TLS configured).
    if (-not [string]::IsNullOrWhiteSpace($env:RESTORE_PGSSLMODE)) {
        $restoreSslMode = $env:RESTORE_PGSSLMODE
    }
    elseif ($sameEndpoint) { $restoreSslMode = $env:PGSSLMODE }
    else { $restoreSslMode = "prefer" }
    if ($restoreSslMode -notin @("verify-full", "verify-ca", "require", "prefer")) {
        throw "RESTORE_PGSSLMODE must be verify-full, verify-ca, require, or prefer."
    }

    # Restore password: $env:RESTORE_PGPASSWORD, else reuse the source password
    # when host/port/user match, else prompt separately.
    if (-not [string]::IsNullOrWhiteSpace($env:RESTORE_PGPASSWORD)) {
        $restorePassword = $env:RESTORE_PGPASSWORD
    }
    elseif (-not $sameEndpoint -or $RestoreUser -ne $DatabaseUser) {
        $secure = Read-Host -AsSecureString "PostgreSQL password for restore user $RestoreUser (${RestoreHost}:${RestorePort})"
        $restorePassword = Convert-SecureToPlain $secure
    }
    else {
        $restorePassword = $env:PGPASSWORD
    }

    if ($RecreateRestoreDatabase) {
        $dropdb = & $resolve "dropdb"
        $createdb = & $resolve "createdb"
        Write-Host "Recreating restore database $RestoreTestDatabase"
        $env:PGPASSWORD = $restorePassword
        $env:PGSSLMODE = $restoreSslMode
        try {
            & $dropdb -h $RestoreHost -p $RestorePort -U $RestoreUser --if-exists --force $RestoreTestDatabase
            if ($LASTEXITCODE -ne 0) { throw "dropdb failed with exit code $LASTEXITCODE" }
            & $createdb -h $RestoreHost -p $RestorePort -U $RestoreUser $RestoreTestDatabase
            if ($LASTEXITCODE -ne 0) { throw "createdb failed with exit code $LASTEXITCODE (restore user needs CREATEDB privilege)" }
        }
        finally {
            $env:PGPASSWORD = $sourcePw
            $env:PGSSLMODE = $sourceSslMode
        }
    }

    $env:PGSSLMODE = $restoreSslMode
    try {
        # Live server identity: catches host aliases that reach the very same
        # server AND database. server_key = server port + postmaster start
        # time identifies the server instance regardless of the interface used.
        $restoreServerKey = (Invoke-Psql @("-h", $RestoreHost, "-p", "$RestorePort", "-U", $RestoreUser, "-d", $RestoreTestDatabase, "-tAc", "SELECT current_setting('port') || '#' || pg_postmaster_start_time()::text") $restorePassword)
        if ($null -eq $restoreServerKey) { throw "could not connect to the restore target $RestoreUser@${RestoreHost}:${RestorePort}/$RestoreTestDatabase" }
        $restoreDb = (Invoke-Psql @("-h", $RestoreHost, "-p", "$RestorePort", "-U", $RestoreUser, "-d", $RestoreTestDatabase, "-tAc", "SELECT current_database()") $restorePassword)
    }
    finally {
        $env:PGSSLMODE = $sourceSslMode
    }
    $sourceServerKey = (Invoke-Psql @("-tAc", "SELECT current_setting('port') || '#' || pg_postmaster_start_time()::text") $sourcePw)
    if ($null -eq $sourceServerKey) { throw "could not read the source server identity" }
    $sourceDb = (Invoke-Psql @("-tAc", "SELECT current_database()") $sourcePw)
    if (($restoreServerKey.Trim() -eq $sourceServerKey.Trim()) -and ($restoreDb -eq $sourceDb)) {
        throw "Refusing to restore: the restore target is the SAME server and database as the source ($sourceDb, server key $($sourceServerKey.Trim()))."
    }

    $env:PGSSLMODE = $restoreSslMode
    try {
        $restoreServerVersion = (Invoke-Psql @("-h", $RestoreHost, "-p", "$RestorePort", "-U", $RestoreUser, "-d", $RestoreTestDatabase, "-tAc", "SHOW server_version") $restorePassword)
        if ($null -eq $restoreServerVersion) { throw "could not read the restore server version" }
    }
    finally {
        $env:PGSSLMODE = $sourceSslMode
    }
    $restoreServerVersion = $restoreServerVersion.Trim()
    $restoreMajor = [int](($restoreServerVersion -split "\.")[0])
    Write-Host "restore : PostgreSQL $restoreServerVersion (${RestoreHost}:${RestorePort}/$RestoreTestDatabase, ssl=$restoreSslMode)"
    if ($restoreMajor -lt $serverMajor) {
        throw "Restore server ($restoreMajor) is older than the source server ($serverMajor); restoring that dump is not supported."
    }
}

# ---- Dump, validate, checksum ---------------------------------------------
if (-not (Test-Path $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$archive = Join-Path $OutputDirectory ("render_{0}_{1}.dump" -f $DatabaseName, $timestamp)
$archivePart = "$archive.part"

try {
    Write-Host "Dumping $DatabaseName -> $archive"
    & $pgDump -h $DatabaseHost -p $DatabasePort -U $DatabaseUser -d $DatabaseName `
        --format=custom --no-owner --no-privileges --file="$archivePart"
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

    Write-Host "Validating archive table of contents"
    & $pgRestore --list "$archivePart" | Out-File -FilePath "$archive.toc.txt" -Encoding utf8 -Width 4096
    if ($LASTEXITCODE -ne 0) { throw "pg_restore --list failed with exit code $LASTEXITCODE" }

    Move-Item -Path $archivePart -Destination $archive -Force

    $hash = (Get-FileHash -Algorithm SHA256 -Path $archive).Hash
    $size = (Get-Item $archive).Length
    $tocLines = (Get-Content "$archive.toc.txt" | Measure-Object -Line).Lines
    Set-Content -Path "$archive.sha256" -Value ("{0}  {1}" -f $hash.ToLower(), (Split-Path $archive -Leaf))

    # ---- Restore drill + structural and row-count verification -----------
    if ($RestoreTest) {
        Write-Host "Restore drill into isolated database $RestoreTestDatabase"
        $env:PGPASSWORD = $restorePassword
        $env:PGSSLMODE = $restoreSslMode
        try {
            & $pgRestore --exit-on-error --no-owner --no-privileges -h $RestoreHost -p $RestorePort `
                -U $RestoreUser -d $RestoreTestDatabase "$archive"
            if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }
        }
        finally {
            $env:PGPASSWORD = $sourcePw
            $env:PGSSLMODE = $sourceSslMode
        }

        $compareSql = @"
SELECT jsonb_build_object(
 'tables', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', tablename) ORDER BY schemaname, tablename) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'columns', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', table_schema, 'table', table_name, 'ordinal', ordinal_position, 'column', column_name, 'type', data_type, 'udt', udt_name, 'nullable', is_nullable, 'default', column_default, 'identity', identity_generation, 'generated', is_generated, 'generation_expression', generation_expression) ORDER BY table_schema, table_name, ordinal_position) FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'views', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', viewname, 'definition', definition) ORDER BY schemaname, viewname) FROM (SELECT schemaname, viewname, definition FROM pg_catalog.pg_views WHERE schemaname NOT IN ('pg_catalog','information_schema')) v), '[]'::jsonb),
 'indexes', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', indexname, 'definition', indexdef) ORDER BY schemaname, indexname) FROM pg_catalog.pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'constraints', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', n.nspname, 'table', c.relname, 'name', con.conname, 'type', con.contype, 'definition', pg_catalog.pg_get_constraintdef(con.oid, true)) ORDER BY n.nspname, c.relname, con.conname) FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'alembic_version_table_present', (to_regclass('public.alembic_version') IS NOT NULL),
 'alembic_version', CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 'null'::jsonb ELSE (SELECT COALESCE(jsonb_agg(version_num ORDER BY version_num), '[]'::jsonb) FROM public.alembic_version) END
)::text;
"@
        $sourceSchema = (Invoke-Psql @("-d", $DatabaseName, "-tAc", $compareSql) $sourcePw)
        if ($null -eq $sourceSchema) { throw "could not read the source schema metadata" }
        $env:PGSSLMODE = $restoreSslMode
        try {
            $restoredSchema = (Invoke-Psql @("-h", $RestoreHost, "-p", "$RestorePort", "-U", $RestoreUser, "-d", $RestoreTestDatabase, "-tAc", $compareSql) $restorePassword)
            if ($null -eq $restoredSchema) { throw "could not read the restored schema metadata" }
        }
        finally {
            $env:PGSSLMODE = $sourceSslMode
        }
        if ($sourceSchema.Trim() -cne $restoredSchema.Trim()) {
            throw "Restore verification failed: column/view/index/constraint/Alembic metadata differs."
        }

        $tableCount = 0
        $tableList = @(& $psql -X -v ON_ERROR_STOP=1 -d $DatabaseName -tA -F "|" -c "SELECT schemaname || '|' || tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename")
        if ($LASTEXITCODE -ne 0) { throw "could not enumerate source tables" }
        foreach ($entry in $tableList) {
            if ([string]::IsNullOrWhiteSpace($entry)) { continue }
            $parts = $entry.Split("|", 2)
            if ($parts.Count -ne 2) { throw "unexpected table inventory result" }
            $tableCount++
            $schemaName = $parts[0].Replace('"', '""')
            $tableName = $parts[1].Replace('"', '""')
            $countQuery = "SELECT count(*) FROM `"$schemaName`".`"$tableName`""
            $sourceCount = (Invoke-Psql @("-d", $DatabaseName, "-tAc", $countQuery) $sourcePw)
            if ($null -eq $sourceCount) { throw "could not count source table $($parts[0]).$($parts[1])" }
            $env:PGSSLMODE = $restoreSslMode
            try {
                $restoredCount = (Invoke-Psql @("-h", $RestoreHost, "-p", "$RestorePort", "-U", $RestoreUser, "-d", $RestoreTestDatabase, "-tAc", $countQuery) $restorePassword)
                if ($null -eq $restoredCount) { throw "could not count restored table $($parts[0]).$($parts[1])" }
            }
            finally {
                $env:PGSSLMODE = $sourceSslMode
            }
            if ($sourceCount.Trim() -ne $restoredCount.Trim()) {
                throw "Restore verification failed: row-count mismatch for $($parts[0]).$($parts[1]) (source=$($sourceCount.Trim()) restored=$($restoredCount.Trim()))."
            }
        }
        $restoreVerified = "PASSED ($tableCount tables: columns/views/indexes/constraints/Alembic state and all table row counts match)"
    }
}
finally {
    if (Test-Path $archivePart) {
        Remove-Item -Force $archivePart
        Write-Warning "Removed incomplete dump $archivePart"
    }
}

Write-Host ""
Write-Host "==== BACKUP RESULT ===="
Write-Host "Archive     : $archive"
Write-Host ("Size        : {0:N0} bytes" -f $size)
Write-Host "SHA-256     : $hash"
Write-Host "TOC entries : $tocLines lines ($archive.toc.txt)"
Write-Host "Restore test: $restoreVerified"
Write-Host "Source      : PostgreSQL $serverVersion (${DatabaseHost}:${DatabasePort}/$DatabaseName)"
