"""Offline regression checks for backup/restore verification safety invariants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSIX_SCRIPT = ROOT / "scripts" / "backup_render_db.sh"
POWERSHELL_SCRIPT = ROOT / "scripts" / "backup_render_db.ps1"
RUNBOOK = ROOT / "docs" / "DB_BACKUP_RUNBOOK.md"


def test_posix_restore_guard_and_tls_requirement() -> None:
    script = POSIX_SCRIPT.read_text(encoding="utf-8")
    assert 'PGSSLMODE="${PGSSLMODE:-verify-full}"' in script
    assert "PGSSLMODE must require TLS" in script
    assert 'RESTORE_TEST_DATABASE" = "$PGDATABASE' in script
    assert '"$PG_RESTORE" --exit-on-error' in script or "--exit-on-error" in script
    assert "information_schema.columns" in script
    assert "'definition', definition" in script
    assert "to_regclass('public.alembic_version')" in script


def test_powershell_restore_guard_and_tls_requirement() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")
    assert '$env:PGSSLMODE = "verify-full"' in script
    assert "PGSSLMODE must require TLS" in script
    assert "$RestoreTestDatabase -eq $DatabaseName" in script
    assert "--exit-on-error" in script
    assert "information_schema.columns" in script
    assert "'definition', definition" in script
    assert "to_regclass('public.alembic_version')" in script


def test_restore_verification_checks_structure_and_rows() -> None:
    for path in (POSIX_SCRIPT, POWERSHELL_SCRIPT):
        script = path.read_text(encoding="utf-8").lower()
        assert "pg_indexes" in script
        assert "pg_constraint" in script
        assert "alembic_version" in script
        assert "row-count mismatch" in script or "row count mismatch" in script


def test_posix_locates_tools_without_path_change() -> None:
    script = POSIX_SCRIPT.read_text(encoding="utf-8")
    assert "PG_BIN" in script
    assert 'PG_DUMP="$probe/pg_dump"' in script
    # PATH is only a last-resort fallback after an explicit directory.
    assert script.index("PG_BIN") < script.index('command -v "$tool"')


def test_powershell_locates_tools_without_path_change() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")
    assert "PostgresBin" in script
    assert "$env:PGBIN" in script
    assert "C:\\Program Files\\PostgreSQL" in script
    # Default install locations are probed before the PATH fallback.
    assert script.index("candidateDirs") < script.index("Get-Command $tool")


def test_posix_restore_connection_is_independent_from_source() -> None:
    script = POSIX_SCRIPT.read_text(encoding="utf-8")
    for var in ("RESTORE_PGHOST", "RESTORE_PGPORT", "RESTORE_PGUSER", "RESTORE_PGPASSWORD"):
        assert var in script
    # The drill client helper always applies the drill endpoint.
    assert '"$@" -h "$RESTORE_PGHOST" -p "$RESTORE_PGPORT" -U "$RESTORE_PGUSER"' in script
    # Recreate capability exists and is guarded to the drill database only.
    assert "RECREATE_RESTORE_DATABASE" in script
    assert "$DROPDB" in script and "$CREATEDB" in script


def test_powershell_restore_connection_is_independent_from_source() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")
    for var in ("$RestoreHost", "$RestorePort", "$RestoreUser", "RESTORE_PGPASSWORD"):
        assert var in script
    assert "RecreateRestoreDatabase" in script
    assert "$dropdb" in script and "$createdb" in script


def test_both_refuse_source_target_via_live_server_identity() -> None:
    """The guard must compare live server identity, not only configured names."""
    for path in (POSIX_SCRIPT, POWERSHELL_SCRIPT):
        script = path.read_text(encoding="utf-8")
        assert "pg_postmaster_start_time" in script
        assert "current_setting('port')" in script
        assert "SAME server and database as the source" in script


def test_both_reject_system_databases_and_bad_names_as_drill_target() -> None:
    for path in (POSIX_SCRIPT, POWERSHELL_SCRIPT):
        script = path.read_text(encoding="utf-8")
        assert "template0" in script and "template1" in script
        assert "postgres" in script
        assert "[A-Za-z_][A-Za-z0-9_]{0,62}" in script


def test_both_check_client_and_restore_server_version_compatibility() -> None:
    for path in (POSIX_SCRIPT, POWERSHELL_SCRIPT):
        script = path.read_text(encoding="utf-8")
        assert "server_major" in script or "serverMajor" in script
        assert "restore_major" in script or "restoreMajor" in script
        assert "older than" in script


def test_runbook_keeps_live_recovery_unverified_and_documents_consistency() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "Live Render backup and restore remain **NOT VERIFIED**" in runbook
    assert "Matching schema metadata and row counts" in runbook
    assert "Never add `0.0.0.0/0`" in runbook
    assert "quiesced" in runbook or "pause writes" in runbook


def test_runbook_documents_laptop_tooling_and_independent_restore_connection() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "PostgreSQL\\18\\bin" in runbook
    assert "PGBIN" in runbook
    assert "RESTORE_PGHOST" in runbook
    assert "pg_postmaster_start_time" in runbook
