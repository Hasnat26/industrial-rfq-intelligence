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
    assert "pg_restore --exit-on-error" in script
    assert "information_schema.columns" in script
    assert "viewname, definition" in script
    assert "to_regclass('public.alembic_version')" in script


def test_powershell_restore_guard_and_tls_requirement() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")
    assert '$env:PGSSLMODE = "verify-full"' in script
    assert "PGSSLMODE must require TLS" in script
    assert '$RestoreTestDatabase -eq $DatabaseName' in script
    assert "pg_restore --exit-on-error" in script
    assert "information_schema.columns" in script
    assert "viewname, definition" in script
    assert "to_regclass('public.alembic_version')" in script


def test_restore_verification_checks_structure_and_rows() -> None:
    for path in (POSIX_SCRIPT, POWERSHELL_SCRIPT):
        script = path.read_text(encoding="utf-8").lower()
        assert "pg_indexes" in script
        assert "pg_constraint" in script
        assert "alembic_version" in script
        assert "row-count mismatch" in script or "row count mismatch" in script


def test_runbook_keeps_live_recovery_unverified_and_documents_consistency() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "Live Render backup and restore remain **NOT VERIFIED**" in runbook
    assert "Matching schema metadata and row counts" in runbook
    assert "Never add `0.0.0.0/0`" in runbook
    assert "quiesced" in runbook or "pause writes" in runbook
