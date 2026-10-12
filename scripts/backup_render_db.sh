#!/usr/bin/env bash
# Logical backup + archive validation (+ optional isolated restore drill) for
# the Industrial RFQ Intelligence Render PostgreSQL database.
#
# POSIX twin of scripts/backup_render_db.ps1 with the identical safety
# properties:
#   * PostgreSQL tools are located WITHOUT any PATH change: PG_BIN (or the
#     first positional argument) names the tools directory; PATH is only a
#     last-resort fallback.
#   * The SOURCE connection and the RESTORE-DRILL connection are fully
#     independent (host, port, user, password, database may all differ).
#   * A restore into the source database is refused twice: from the
#     configured parameters AND from the live server identity reported by
#     each connection (port + pg_postmaster_start_time), which catches the
#     same server/database reached through a different interface or alias
#     (127.0.0.1 vs localhost vs IPv6 loopback vs DNS names).
#   * The source connection must use TLS (PGSSLMODE verify-full by default).
#   * Archives are published only after pg_restore --list validation and are
#     recorded with a SHA-256 checksum.
#   * Restore drills verify table/column inventories, view/index/constraint
#     definitions, Alembic revision state, and per-table row counts.
#
# Credentials: set PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD as session
# environment variables (e.g. `read -s PGPASSWORD; export PGPASSWORD` so the
# value is never typed into argv or shell history). The drill may use
# RESTORE_PGHOST/RESTORE_PGPORT/RESTORE_PGUSER/RESTORE_TEST_DATABASE with
# RESTORE_PGPASSWORD (defaults: reuse the source values when the endpoint
# matches). Set RECREATE_RESTORE_DATABASE=1 to drop and recreate the drill
# database first (the restore user then needs CREATEDB/CREATEDB right on the
# drill server). This script never prints secret values.
#
# Usage:
#   PGHOST=... PGUSER=... PGDATABASE=... ./scripts/backup_render_db.sh [PG_BIN_DIR]
#   ... plus RESTORE_TEST_DATABASE=ffp_restore_test for an isolated drill.
set -euo pipefail

# Session-only libpq credentials. Never broaden the database allowlist.
: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"
PGPORT="${PGPORT:-5432}"
PGSSLMODE="${PGSSLMODE:-verify-full}"
if [ -z "${PGPASSWORD:-}" ]; then
  echo "PGPASSWORD is required (set it in the session environment)." >&2
  exit 1
fi
case "$PGSSLMODE" in
  verify-full|verify-ca|require) ;;
  *) echo "ERROR: PGSSLMODE must require TLS." >&2; exit 1 ;;
esac
export PGSSLMODE

OUTPUT_DIR="${OUTPUT_DIR:-./backups}"

# ---- Locate PostgreSQL tools (no PATH modification required) --------------
if [ -n "${PG_BIN:-}" ]; then
  probe="$PG_BIN"
elif [ -n "${1:-}" ]; then
  probe="$1"
else
  probe=""
fi
if [ -n "$probe" ]; then
  for tool in pg_dump pg_restore psql createdb dropdb; do
    if [ ! -x "$probe/$tool" ]; then
      echo "ERROR: $tool is not executable at $probe/$tool" >&2
      exit 1
    fi
  done
  PG_DUMP="$probe/pg_dump"; PG_RESTORE="$probe/pg_restore"; PSQL="$probe/psql"
  CREATEDB="$probe/createdb"; DROPDB="$probe/dropdb"
else
  for tool in pg_dump pg_restore psql createdb dropdb; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "ERROR: $tool not found on PATH. Set PG_BIN to the tools directory, e.g. PG_BIN=/usr/lib/postgresql/16/bin" >&2
      exit 1
    fi
  done
  PG_DUMP="pg_dump"; PG_RESTORE="pg_restore"; PSQL="psql"
  CREATEDB="createdb"; DROPDB="dropdb"
fi
echo "PostgreSQL tools: ${probe:-PATH}"

# ---- Source version guard -------------------------------------------------
tool_version="$("$PG_DUMP" --version)"
server_version="$("$PSQL" -X -v ON_ERROR_STOP=1 -tAc 'SHOW server_version' | sed -E 's/[[:space:]]+$//')"
tool_major="$(echo "$tool_version" | sed -E 's/.*PostgreSQL\) ([0-9]+).*/\1/')"
server_major="${server_version%%.*}"
echo "pg_dump: $tool_version"
echo "source  : PostgreSQL $server_version ($PGHOST:$PGPORT/$PGDATABASE)"
if [ "$tool_major" -lt "$server_major" ]; then
  echo "ERROR: pg_dump major ($tool_major) is older than server major ($server_major)." >&2
  exit 1
fi

# ---- Restore-drill guards (BEFORE any dump or destructive action) ---------
RESTORE_TEST_DATABASE="${RESTORE_TEST_DATABASE:-}"
restore_verified="not requested"
if [ -n "$RESTORE_TEST_DATABASE" ]; then
  if ! printf '%s' "$RESTORE_TEST_DATABASE" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]{0,62}$'; then
    echo "ERROR: invalid restore database name '$RESTORE_TEST_DATABASE'" >&2
    exit 1
  fi
  case "$RESTORE_TEST_DATABASE" in
    postgres|template0|template1)
      echo "ERROR: refusing to use system database '$RESTORE_TEST_DATABASE' as the restore target." >&2
      exit 1 ;;
  esac
  RESTORE_PGHOST="${RESTORE_PGHOST:-$PGHOST}"
  RESTORE_PGPORT="${RESTORE_PGPORT:-$PGPORT}"
  RESTORE_PGUSER="${RESTORE_PGUSER:-$PGUSER}"
  if [ "$RESTORE_PGHOST" = "$PGHOST" ] && [ "$RESTORE_PGPORT" = "$PGPORT" ] \
    && [ "$RESTORE_TEST_DATABASE" = "$PGDATABASE" ]; then
    echo "ERROR: refusing to restore into source database '$PGDATABASE'." >&2
    exit 1
  fi
  if [ -n "${RESTORE_PGPASSWORD:-}" ]; then
    restore_password="$RESTORE_PGPASSWORD"
  else
    restore_password="$PGPASSWORD"
  fi
  # Source-like endpoints keep TLS; a different (typically local) drill
  # endpoint defaults to "prefer" so plaintext local drills work while any
  # operator-set value is still validated below.
  if [ -n "${RESTORE_PGSSLMODE:-}" ]; then
    RESTORE_PGSSLMODE="$RESTORE_PGSSLMODE"
  elif [ "$RESTORE_PGHOST" = "$PGHOST" ] && [ "$RESTORE_PGPORT" = "$PGPORT" ]; then
    RESTORE_PGSSLMODE="$PGSSLMODE"
  else
    RESTORE_PGSSLMODE="prefer"
  fi
  case "$RESTORE_PGSSLMODE" in
    verify-full|verify-ca|require|prefer) ;;
    *) echo "ERROR: RESTORE_PGSSLMODE must be verify-full, verify-ca, require, or prefer." >&2; exit 1 ;;
  esac

  as_restore() { # run a drill client with the drill credentials
    PGPASSWORD="$restore_password" PGSSLMODE="$RESTORE_PGSSLMODE" \
      "$@" -h "$RESTORE_PGHOST" -p "$RESTORE_PGPORT" -U "$RESTORE_PGUSER"
  }

  if [ "${RECREATE_RESTORE_DATABASE:-0}" = "1" ]; then
    echo "Recreating restore database $RESTORE_TEST_DATABASE"
    as_restore "$DROPDB" --if-exists --force "$RESTORE_TEST_DATABASE"
    as_restore "$CREATEDB" "$RESTORE_TEST_DATABASE"
  fi

  # Live server identity: port + postmaster start time identify the server
  # instance regardless of which interface or alias was used to reach it.
  source_server_key="$("$PSQL" -X -v ON_ERROR_STOP=1 -tAc "SELECT current_setting('port') || '#' || pg_postmaster_start_time()::text")"
  source_db="$("$PSQL" -X -v ON_ERROR_STOP=1 -tAc 'SELECT current_database()')"
  restore_server_key="$(as_restore "$PSQL" -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc "SELECT current_setting('port') || '#' || pg_postmaster_start_time()::text")"
  restore_db="$(as_restore "$PSQL" -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc 'SELECT current_database()')"
  if [ "$restore_server_key" = "$source_server_key" ] && [ "$restore_db" = "$source_db" ]; then
    echo "ERROR: refusing to restore: the restore target is the SAME server and database as the source ($source_db, server key $source_server_key)." >&2
    exit 1
  fi

  restore_server_version="$(as_restore "$PSQL" -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc 'SHOW server_version' | sed -E 's/[[:space:]]+$//')"
  restore_major="${restore_server_version%%.*}"
  echo "restore : PostgreSQL $restore_server_version ($RESTORE_PGHOST:$RESTORE_PGPORT/$RESTORE_TEST_DATABASE, ssl=$RESTORE_PGSSLMODE)"
  if [ "$restore_major" -lt "$server_major" ]; then
    echo "ERROR: restore server ($restore_major) is older than the source server ($server_major); restoring that dump is not supported." >&2
    exit 1
  fi
fi

# ---- Dump, validate, checksum ---------------------------------------------
mkdir -p "$OUTPUT_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$OUTPUT_DIR/render_${PGDATABASE}_${timestamp}.dump"
partial="$archive.partial"
toc="$archive.toc.txt"
checksum="$archive.sha256"
trap 'rm -f "$partial"' EXIT

echo "Dumping source database to temporary archive"
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  --format=custom --no-owner --no-privileges --file="$partial"
test -s "$partial"
pg_restore --list "$partial" > "$toc"
mv -- "$partial" "$archive"

sha256="$(sha256sum "$archive" | awk '{print $1}')"
printf '%s  %s\n' "$sha256" "$(basename "$archive")" > "$checksum"
toc_lines="$(wc -l < "$toc" | tr -d ' ')"
size="$(stat -c%s "$archive" 2>/dev/null || stat -f%z "$archive")"

# ---- Restore drill + structural and row-count verification ----------------
if [ -n "$RESTORE_TEST_DATABASE" ]; then
  echo "Restore drill into isolated database $RESTORE_TEST_DATABASE"
  as_restore "$PG_RESTORE" --exit-on-error --no-owner --no-privileges \
    -d "$RESTORE_TEST_DATABASE" "$archive"

  compare_sql=$(cat <<'SQL'
SELECT jsonb_build_object(
 'tables', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', tablename) ORDER BY schemaname, tablename) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'columns', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', table_schema, 'table', table_name, 'ordinal', ordinal_position, 'column', column_name, 'type', data_type, 'udt', udt_name, 'nullable', is_nullable, 'default', column_default, 'identity', identity_generation, 'generated', is_generated, 'generation_expression', generation_expression) ORDER BY table_schema, table_name, ordinal_position) FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'views', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', viewname, 'definition', definition) ORDER BY schemaname, viewname) FROM (SELECT schemaname, viewname, definition FROM pg_catalog.pg_views WHERE schemaname NOT IN ('pg_catalog','information_schema')) v), '[]'::jsonb),
 'indexes', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', indexname, 'definition', indexdef) ORDER BY schemaname, indexname) FROM pg_catalog.pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'constraints', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', n.nspname, 'table', c.relname, 'name', con.conname, 'type', con.contype, 'definition', pg_catalog.pg_get_constraintdef(con.oid, true)) ORDER BY n.nspname, c.relname, con.conname) FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'alembic_version_table_present', (to_regclass('public.alembic_version') IS NOT NULL),
 'alembic_version', CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 'null'::jsonb ELSE (SELECT COALESCE(jsonb_agg(version_num ORDER BY version_num), '[]'::jsonb) FROM public.alembic_version) END
)::text;
SQL
)
  source_schema="$("$PSQL" -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tAc "$compare_sql")"
  restored_schema="$(as_restore "$PSQL" -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc "$compare_sql")"
  if [ "$source_schema" != "$restored_schema" ]; then
    echo "ERROR: schema columns, views, indexes, constraints, or Alembic revision differ." >&2
    exit 1
  fi

  source_tables="$("$PSQL" -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tA -F $'\t' -c "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename")"
  table_count=0
  while IFS=$'\t' read -r schema table; do
    [ -n "$schema" ] || continue
    table_count=$((table_count + 1))
    quoted_schema=$(printf '%s' "$schema" | sed 's/"/""/g')
    quoted_table=$(printf '%s' "$table" | sed 's/"/""/g')
    source_count="$("$PSQL" -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tAc "SELECT count(*) FROM \"$quoted_schema\".\"$quoted_table\"")"
    restored_count="$(as_restore "$PSQL" -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc "SELECT count(*) FROM \"$quoted_schema\".\"$quoted_table\"")"
    if [ "$source_count" != "$restored_count" ]; then
      echo "ERROR: row-count mismatch for $schema.$table (source=$source_count restored=$restored_count)." >&2
      exit 1
    fi
  done <<< "$source_tables"
  restore_verified="PASSED ($table_count tables: columns/views/indexes/constraints/Alembic state and all table row counts match)"
fi

echo
echo "==== BACKUP RESULT ===="
echo "Archive     : $archive"
echo "Size        : $size bytes"
echo "SHA-256     : $sha256"
echo "TOC entries : $toc_lines lines ($toc)"
echo "Restore test: $restore_verified"
echo "Source      : PostgreSQL $server_version ($PGHOST:$PGPORT/$PGDATABASE)"
