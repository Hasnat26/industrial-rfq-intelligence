<#
.SYNOPSIS
    Logical backup, archive validation, and optional isolated restore test.
.DESCRIPTION
    Writes a custom-format dump to a temporary file, validates its TOC, and
    publishes the archive with a SHA-256 checksum. Restore validation uses a
    separate pre-created database. The script never creates or drops databases.
#>
[CmdletBinding()]
param(
    [string]$DatabaseHost = $env:PGHOST,
    [int]$DatabasePort = 5432,
    [string]$DatabaseUser = $env:PGUSER,
    [string]$DatabaseName = $env:PGDATABASE,
    [string]$OutputDirectory = (Join-Path (Get-Location) "backups"),
    [switch]$RestoreTest,
    [string]$RestoreTestDatabase
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
    try { $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$env:PGHOST = $DatabaseHost
$env:PGPORT = "$DatabasePort"
$env:PGUSER = $DatabaseUser
$env:PGDATABASE = $DatabaseName
if ([string]::IsNullOrWhiteSpace($env:PGSSLMODE)) { $env:PGSSLMODE = "verify-full" }
if ($env:PGSSLMODE -notin @("verify-full", "verify-ca", "require")) {
    throw "PGSSLMODE must require TLS (verify-full, verify-ca, or require)."
}

$toolVersion = (pg_dump --version)
$serverVersion = (psql -X -v ON_ERROR_STOP=1 -tAc "SHOW server_version").Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to query PostgreSQL server version." }
$toolMajor = [int](($toolVersion -split "pg_dump \(PostgreSQL\) ")[1].Split(".")[0])
$serverMajor = [int](($serverVersion -split "\.")[0])
Write-Host "pg_dump: $toolVersion"
Write-Host "server : PostgreSQL $serverVersion"
if ($toolMajor -lt $serverMajor) { throw "pg_dump major is older than server major." }
if ($RestoreTest) {
    if ([string]::IsNullOrWhiteSpace($RestoreTestDatabase)) { throw "-RestoreTest requires a separate pre-created target." }
    if ($RestoreTestDatabase -eq $DatabaseName) { throw "Refusing to restore into source database '$DatabaseName'." }
}

if (-not (Test-Path $OutputDirectory)) { New-Item -ItemType Directory -Path $OutputDirectory | Out-Null }
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$archive = Join-Path $OutputDirectory ("render_{0}_{1}.dump" -f $DatabaseName, $timestamp)
$partial = "$archive.partial"
$tocPath = "$archive.toc.txt"
$checksumPath = "$archive.sha256"
try {
    & pg_dump -h $DatabaseHost -p $DatabasePort -U $DatabaseUser -d $DatabaseName --format=custom --no-owner --no-privileges --file="$partial"
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path $partial) -or (Get-Item $partial).Length -eq 0) { throw "pg_dump produced an empty archive." }
    & pg_restore --list "$partial" | Out-File -FilePath $tocPath -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "pg_restore --list failed with exit code $LASTEXITCODE" }
    Move-Item -LiteralPath $partial -Destination $archive
    $hash = (Get-FileHash -Algorithm SHA256 -Path $archive).Hash
    $size = (Get-Item $archive).Length
    $tocLines = (Get-Content $tocPath | Measure-Object -Line).Lines
    Set-Content -Path $checksumPath -Value ("{0}  {1}" -f $hash, (Split-Path $archive -Leaf))

    $restoreVerified = "not requested"
    if ($RestoreTest) {
        & pg_restore --exit-on-error --no-owner --no-privileges -h $DatabaseHost -p $DatabasePort -U $DatabaseUser -d $RestoreTestDatabase "$archive"
        if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }
        $schemaSql = @"
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
        $sourceSchema = (psql -X -v ON_ERROR_STOP=1 -d $DatabaseName -tAc $schemaSql).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Failed to inspect source schema metadata." }
        $restoredSchema = (psql -X -v ON_ERROR_STOP=1 -d $RestoreTestDatabase -tAc $schemaSql).Trim()
        if ($LASTEXITCODE -ne 0) { throw "Failed to inspect restored schema metadata." }
        if ($sourceSchema -cne $restoredSchema) { throw "Restore verification failed: column/view/index/constraint/Alembic metadata differs." }
        $tables = (psql -X -v ON_ERROR_STOP=1 -d $DatabaseName -tA -F "|" -c "SELECT schemaname || '|' || tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename")
        if ($LASTEXITCODE -ne 0) { throw "Failed to enumerate source tables." }
        foreach ($line in $tables) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $parts = $line.Split("|", 2)
            if ($parts.Count -ne 2) { throw "Unexpected table inventory result." }
            $schemaName = $parts[0].Replace('"','""')
            $tableName = $parts[1].Replace('"','""')
            $sourceCount = (psql -X -v ON_ERROR_STOP=1 -d $DatabaseName -tAc "SELECT count(*) FROM `"$schemaName`".`"$tableName`"").Trim()
            if ($LASTEXITCODE -ne 0) { throw "Failed counting source table." }
            $restoredCount = (psql -X -v ON_ERROR_STOP=1 -d $RestoreTestDatabase -tAc "SELECT count(*) FROM `"$schemaName`".`"$tableName`"").Trim()
            if ($LASTEXITCODE -ne 0) { throw "Failed counting restored table." }
            if ($sourceCount -ne $restoredCount) { throw "Restore verification failed: row-count mismatch for $($parts[0]).$($parts[1])." }
        }
        $restoreVerified = "PASSED (columns/views/indexes/constraints/Alembic state and all table row counts match)"
    }
    Write-Host "Archive     : $archive"
    Write-Host ("Size        : {0:N0} bytes" -f $size)
    Write-Host "SHA-256     : $hash"
    Write-Host "TOC entries : $tocLines lines ($tocPath)"
    Write-Host "Restore test: $restoreVerified"
    Write-Host "Server      : PostgreSQL $serverVersion"
}
finally {
    if (Test-Path $partial) { Remove-Item -LiteralPath $partial -Force }
}
