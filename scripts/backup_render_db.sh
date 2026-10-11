#!/usr/bin/env bash
# Logical backup + archive validation (+ optional isolated restore drill) for
# the Industrial RFQ Intelligence Render PostgreSQL database.
#
# POSIX twin of scripts/backup_render_db.ps1; the exact command sequence in
# this script was drill-tested against a scratch PostgreSQL instance
# (dump -> pg_restore --list -> restore into a separate database -> table
# count comparison). Run it from a shell where PostgreSQL client tools
# (pg_dump/pg_restore/psql) are on PATH, e.g. the Windows laptop's
# PostgreSQL 18.6 tools under Git Bash or WSL.
#
# Credentials: set PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD as session
# environment variables before running (e.g. `read -s PGPASSWORD; export
# PGPASSWORD` so the value is never typed into argv or shell history).
# This script never prints secret values.
#
# Usage:
#   PGHOST=... PGUSER=... PGDATABASE=... ./scripts/backup_render_db.sh
#   ... plus RESTORE_TEST_DATABASE=industrial_rfq_restore_test for a drill
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
PGPORT="${PGPORT:-5432}"
if [ -z "${PGPASSWORD:-}" ]; then
  echo "PGPASSWORD is required (set it in the session environment, never on the command line)" >&2
  exit 1
fi

OUTPUT_DIR="${OUTPUT_DIR:-./backups}"

tool_version="$(pg_dump --version)"
server_version="$(psql -tAc 'SHOW server_version' | tr -d '[:space:]')"
tool_major="$(echo "$tool_version" | sed -E 's/.*PostgreSQL\) ([0-9]+).*/\1/')"
server_major="${server_version%%.*}"
echo "pg_dump: $tool_version"
echo "server : PostgreSQL $server_version"
if [ "$tool_major" -lt "$server_major" ]; then
  echo "ERROR: pg_dump major ($tool_major) is older than the server ($server_major); upgrading the client tools is required." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$OUTPUT_DIR/render_${PGDATABASE}_${timestamp}.dump"

echo "Dumping $PGDATABASE -> $archive"
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  --format=custom --no-owner --no-privileges --file="$archive"

echo "Validating archive table of contents"
pg_restore --list "$archive" > "$archive.toc.txt"

sha256="$(sha256sum "$archive" | awk '{print $1}')"
printf '%s  %s\n' "$sha256" "$(basename "$archive")" > "$archive.sha256"
toc_lines="$(wc -l < "$archive.toc.txt" | tr -d ' ')"

restore_verified="not requested"
if [ -n "${RESTORE_TEST_DATABASE:-}" ]; then
  if [ "$RESTORE_TEST_DATABASE" = "$PGDATABASE" ]; then
    echo "ERROR: refusing to restore into the source database '$PGDATABASE'." >&2
    exit 1
  fi
  echo "Restore drill into isolated database $RESTORE_TEST_DATABASE"
  pg_restore --no-owner --no-privileges -h "$PGHOST" -p "$PGPORT" \
    -U "$PGUSER" -d "$RESTORE_TEST_DATABASE" "$archive"
  source_tables="$(psql -tAc "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
  restored_tables="$(psql -d "$RESTORE_TEST_DATABASE" -tAc "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
  if [ "$source_tables" != "$restored_tables" ]; then
    echo "ERROR: restore drill mismatch: source=$source_tables restored=$restored_tables tables" >&2
    exit 1
  fi
  restore_verified="PASSED ($restored_tables application tables restored)"
fi

size="$(stat -c%s "$archive" 2>/dev/null || stat -f%z "$archive")"
echo
echo "==== BACKUP RESULT ===="
echo "Archive     : $archive"
echo "Size        : $size bytes"
echo "SHA-256     : $sha256"
echo "TOC entries : $toc_lines lines ($archive.toc.txt)"
echo "Restore test: $restore_verified"
echo "Server      : PostgreSQL $server_version"
