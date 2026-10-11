<#
.SYNOPSIS
    Logical backup + archive validation (+ optional isolated restore test)
    for the Industrial RFQ Intelligence Render PostgreSQL database.

.DESCRIPTION
    Creates a timestamped custom-format pg_dump archive, validates it with
    pg_restore --list, records a SHA-256 checksum, and (optionally) performs
    a restore drill into a SEPARATE test database. It refuses to restore into
    the source database.

    Credentials are never accepted as command-line arguments (argv is visible
    in process listings). The password is read once via a secure prompt into
    the session environment only; prefer setting PGHOST/PGPORT/PGDATABASE/
    PGUSER/PGPASSWORD as session-scoped $env: variables before running so
    nothing is typed at all.

.EXAMPLE
    $env:PGHOST = "dpg-xxxxx-a.routedb.render.com"
    $env:PGPORT = "5432"
    $env:PGUSER = "industrial_rfq_user"
    $env:PGPASSWORD = Read-Host -Prompt "Render DB password"   # never pasted into chat
    .\scripts\backup_render_db.ps1 -DatabaseName industrial_rfq `
        -RestoreTest -RestoreTestDatabase industrial_rfq_restore_test

.NOTES
    Requires PostgreSQL client tools (pg_dump/pg_restore/psql) on PATH.
    pg_dump must be the SAME OR NEWER major version than the server
    (laptop 18.x tools can dump a 16.x server; the reverse is not supported).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)] [string]$DatabaseHost = $env:PGHOST,
    [Parameter(Mandatory = $false)] [int]$DatabasePort = 5432,
    [Parameter(Mandatory = $false)] [string]$DatabaseUser = $env:PGUSER,
    [Parameter(Mandatory = $false)] [string]$DatabaseName = $env:PGDATABASE,
    [Parameter(Mandatory = $false)] [string]$OutputDirectory = (Join-Path (Get-Location) "backups"),
    [Parameter(Mandatory = $false)] [switch]$RestoreTest,
    [Parameter(Mandatory = $false)] [string]$RestoreTestDatabase
)

$ErrorActionPreference = "Stop"

foreach ($name in @("DatabaseHost", "DatabaseUser", "DatabaseName")) {
    if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $name -ValueOnly))) {
        throw "$name is required (parameter or matching PG* environment variable)."
    }
}

foreach ($tool in @("pg_dump", "pg_restore", "psql")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool was not found on PATH. Install PostgreSQL client tools first."
    }
}

if ([string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
    $secure = Read-Host -AsSecureString "PostgreSQL password for $DatabaseUser"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$env:PGHOST = $DatabaseHost
$env:PGPORT = "$DatabasePort"
$env:PGUSER = $DatabaseUser
$env:PGDATABASE = $DatabaseName

$toolVersion = (pg_dump --version)
$serverVersion = (psql -tAc "SHOW server_version").Trim()
$toolMajor = [int](($toolVersion -split "pg_dump \(PostgreSQL\) ")[1].Split(".")[0])
$serverMajor = [int](($serverVersion -split "\.")[0])
Write-Host "pg_dump: $toolVersion"
Write-Host "server : PostgreSQL $serverVersion"
if ($toolMajor -lt $serverMajor) {
    throw "pg_dump major version ($toolMajor) is older than the server ($serverMajor). Upgrade the client tools; downgrading the dump is not supported."
}

if (-not (Test-Path $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$archive = Join-Path $OutputDirectory ("render_{0}_{1}.dump" -f $DatabaseName, $timestamp)

Write-Host "Dumping $DatabaseName -> $archive"
& pg_dump -h $DatabaseHost -p $DatabasePort -U $DatabaseUser -d $DatabaseName `
    --format=custom --no-owner --no-privileges --file="$archive"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

Write-Host "Validating archive table of contents"
& pg_restore --list "$archive" | Out-File -FilePath "$archive.toc.txt" -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "pg_restore --list failed with exit code $LASTEXITCODE" }

$hash = (Get-FileHash -Algorithm SHA256 -Path $archive).Hash
$size = (Get-Item $archive).Length
$tocLines = (Get-Content "$archive.toc.txt" | Measure-Object -Line).Lines
Set-Content -Path "$archive.sha256" -Value ("{0}  {1}" -f $hash, (Split-Path $archive -Leaf))

$restoreVerified = "not requested"
if ($RestoreTest) {
    if ([string]::IsNullOrWhiteSpace($RestoreTestDatabase)) {
        throw "-RestoreTest requires -RestoreTestDatabase naming a SEPARATE database."
    }
    if ($RestoreTestDatabase -eq $DatabaseName) {
        throw "Refusing to restore into the source database '$DatabaseName'. Use a separate restore-test database."
    }
    Write-Host "Restore drill into isolated database $RestoreTestDatabase"
    & pg_restore --no-owner --no-privileges -h $DatabaseHost -p $DatabasePort `
        -U $DatabaseUser -d $RestoreTestDatabase "$archive"
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }
    $sourceTables = (psql -tAc "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
    $env:PGDATABASE = $RestoreTestDatabase
    $restoredTables = (psql -tAc "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
    $env:PGDATABASE = $DatabaseName
    if ($sourceTables -ne $restoredTables) {
        throw "Restore drill mismatch: source has $sourceTables tables, restored database has $restoredTables."
    }
    $restoreVerified = "PASSED ($restoredTables application tables restored)"
}

Write-Host ""
Write-Host "==== BACKUP RESULT ===="
Write-Host "Archive     : $archive"
Write-Host ("Size        : {0:N0} bytes" -f $size)
Write-Host "SHA-256     : $hash"
Write-Host "TOC entries : $tocLines lines ($archive.toc.txt)"
Write-Host "Restore test: $restoreVerified"
Write-Host "Server      : PostgreSQL $serverVersion"
