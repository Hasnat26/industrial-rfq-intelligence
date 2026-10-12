#!/usr/bin/env bash
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
tool_version="$(pg_dump --version)"
server_version="$(psql -X -v ON_ERROR_STOP=1 -tAc 'SHOW server_version' | tr -d '[:space:]')"
tool_major="$(echo "$tool_version" | sed -E 's/.*PostgreSQL\) ([0-9]+).*/\1/')"
server_major="${server_version%%.*}"
echo "pg_dump: $tool_version"
echo "server : PostgreSQL $server_version"
if [ "$tool_major" -lt "$server_major" ]; then
  echo "ERROR: pg_dump major ($tool_major) is older than server major ($server_major)." >&2
  exit 1
fi

RESTORE_TEST_DATABASE="${RESTORE_TEST_DATABASE:-}"
if [ -n "$RESTORE_TEST_DATABASE" ] && [ "$RESTORE_TEST_DATABASE" = "$PGDATABASE" ]; then
  echo "ERROR: refusing to restore into source database '$PGDATABASE'." >&2
  exit 1
fi

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

restore_verified="not requested"
if [ -n "$RESTORE_TEST_DATABASE" ]; then
  pg_restore --exit-on-error --no-owner --no-privileges -h "$PGHOST" -p "$PGPORT" \
    -U "$PGUSER" -d "$RESTORE_TEST_DATABASE" "$archive"

  compare_sql=$(cat <<'SQL'
SELECT jsonb_build_object(
 'tables', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', tablename) ORDER BY schemaname, tablename) FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'columns', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', table_schema, 'table', table_name, 'ordinal', ordinal_position, 'column', column_name, 'type', data_type, 'udt', udt_name, 'nullable', is_nullable, 'default', column_default, 'identity', identity_generation, 'generated', is_generated, 'generation_expression', generation_expression) ORDER BY table_schema, table_name, ordinal_position) FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'views', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', viewname, 'definition', definition) ORDER BY schemaname, viewname) FROM (SELECT schemaname, viewname, definition FROM pg_catalog.pg_views WHERE schemaname NOT IN ('pg_catalog','information_schema')) v), '[]'::jsonb),
 'indexes', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', schemaname, 'name', indexname, 'definition', indexdef) ORDER BY schemaname, indexname) FROM pg_catalog.pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'constraints', COALESCE((SELECT jsonb_agg(jsonb_build_object('schema', n.nspname, 'table', c.relname, 'name', con.conname, 'type', con.contype, 'definition', pg_catalog.pg_get_constraintdef(con.oid, true) ORDER BY n.nspname, c.relname, con.conname) FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')), '[]'::jsonb),
 'alembic_version_table_present', (to_regclass('public.alembic_version') IS NOT NULL),
 'alembic_version', CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 'null'::jsonb ELSE (SELECT COALESCE(jsonb_agg(version_num ORDER BY version_num), '[]'::jsonb) FROM public.alembic_version) END
)::text;
SQL
)
  source_schema="$(psql -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tAc "$compare_sql")"
  restored_schema="$(psql -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc "$compare_sql")"
  if [ "$source_schema" != "$restored_schema" ]; then
    echo "ERROR: schema columns, views, indexes, constraints, or Alembic revision differ." >&2
    exit 1
  fi

  source_tables="$(psql -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tA -F $'\t' -c "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename")"
  while IFS=$'\t' read -r schema table; do
    [ -n "$schema" ] || continue
    quoted_schema=$(printf '%s' "$schema" | sed 's/"/""/g')
    quoted_table=$(printf '%s' "$table" | sed 's/"/""/g')
    source_count="$(psql -X -v ON_ERROR_STOP=1 -d "$PGDATABASE" -tAc "SELECT count(*) FROM \"$quoted_schema\".\"$quoted_table\"")"
    restored_count="$(psql -X -v ON_ERROR_STOP=1 -d "$RESTORE_TEST_DATABASE" -tAc "SELECT count(*) FROM \"$quoted_schema\".\"$quoted_table\"")"
    if [ "$source_count" != "$restored_count" ]; then
      echo "ERROR: row-count mismatch for $schema.$table (source=$source_count restored=$restored_count)." >&2
      exit 1
    fi
  done <<< "$source_tables"
  restore_verified="PASSED (columns/views/indexes/constraints/Alembic state and all table row counts match)"
fi

echo
echo "==== BACKUP RESULT ===="
echo "Archive     : $archive"
echo "Size        : $size bytes"
echo "SHA-256     : $sha256"
echo "TOC entries : $toc_lines lines ($toc)"
echo "Restore test: $restore_verified"
echo "Server      : PostgreSQL $server_version"
