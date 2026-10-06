"""Alembic migration tests: clean upgrades, dev-schema adoption, app startup.

All tests run against throwaway databases under ``tmp_path``; the repository's
development SQLite file is never touched.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "organizations",
    "users",
    "auth_sessions",
    "organization_memberships",
    "projects",
    "procurement_packages",
    "rfq_revisions",
    "requirements",
    "vendor_offers",
    "technical_clarifications",
    "technical_deviations",
    "vendor_documents",
    "vendor_claims",
    "vendor_document_pages",
    "package_evaluation_settings",
    "asset_products",
    "organization_subscriptions",
    "usage_records",
    "billing_webhook_events",
    "commercial_reconciliation_runs",
    "lifecycle_events",
    "procurement_decisions",
    "procurement_audit_events",
    "lifecycle_cost_records",
}


def _run(args: list[str], db_path: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "INDUSTRIAL_RFQ_DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"command {args} failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    return _run(["-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), *args], db_path)


def _tables(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connection.close()
    return {name for (name,) in rows}


def test_migration_upgrades_a_clean_database(tmp_path: Path) -> None:
    database = tmp_path / "clean.db"
    _alembic("upgrade", "head", db_path=database)
    tables = _tables(database)
    assert EXPECTED_TABLES <= tables, EXPECTED_TABLES - tables
    assert "alembic_version" in tables


def test_migration_downgrade_and_upgrade_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "roundtrip.db"
    _alembic("upgrade", "head", db_path=database)
    _alembic("downgrade", "base", db_path=database)
    remaining = _tables(database)
    assert not EXPECTED_TABLES & remaining, EXPECTED_TABLES & remaining
    _alembic("upgrade", "head", db_path=database)
    assert EXPECTED_TABLES <= _tables(database)


def test_migration_adopts_existing_development_schema_without_data_loss(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.db"
    legacy_setup = (
        "from freellmpool.api.db import Base, Organization, SessionLocal, engine\n"
        "Base.metadata.create_all(bind=engine)\n"
        "db = SessionLocal()\n"
        "db.add(Organization(name='Legacy Dev Org'))\n"
        "db.commit()\n"
        "db.close()\n"
    )
    _run(["-c", legacy_setup], database)

    # An existing development database is adopted by stamping, then upgraded.
    _alembic("stamp", "head", db_path=database)
    before = _tables(database)
    _alembic("upgrade", "head", db_path=database)
    assert _tables(database) == before

    connection = sqlite3.connect(database)
    try:
        names = [row[0] for row in connection.execute("SELECT name FROM organizations")]
    finally:
        connection.close()
    assert names == ["Legacy Dev Org"]


def test_application_starts_against_migrated_database(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    _alembic("upgrade", "head", db_path=database)
    smoke = (
        "from fastapi.testclient import TestClient\n"
        "from freellmpool.api.app import app\n"
        "with TestClient(app) as client:\n"
        "    assert client.get('/health').status_code == 200\n"
        "    registered = client.post('/auth/register', "
        "json={'email': 'migrated@example.com', 'password': 'migrated-secret-1'})\n"
        "    assert registered.status_code == 201, registered.text\n"
        "    logged_in = client.post('/auth/login', "
        "json={'email': 'migrated@example.com', 'password': 'migrated-secret-1'})\n"
        "    assert logged_in.status_code == 200, logged_in.text\n"
        "    headers = {'Authorization': 'Bearer ' + logged_in.json()['access_token']}\n"
        "    org = client.post('/organizations', json={'name': 'Migrated Org'}, "
        "headers=headers)\n"
        "    assert org.status_code == 201, org.text\n"
    )
    _run(["-c", smoke], database)


def test_production_configuration_fails_closed(monkeypatch) -> None:
    from freellmpool.api.app import _validate_production_configuration

    monkeypatch.setenv("INDUSTRIAL_RFQ_ENV", "production")
    monkeypatch.setenv("INDUSTRIAL_RFQ_DATABASE_URL", "sqlite:///./unsafe.db")
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "x" * 32)
    monkeypatch.setenv("INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET", "y" * 32)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        _validate_production_configuration()

    monkeypatch.setenv("INDUSTRIAL_RFQ_DATABASE_URL", "postgresql://user:pass@localhost/production")
    monkeypatch.setenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES", "1")
    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES"):
        _validate_production_configuration()

    monkeypatch.setenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES", "0")
    monkeypatch.setenv("INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET", "short")
    with pytest.raises(RuntimeError, match="INTERNAL_RECONCILIATION_SECRET"):
        _validate_production_configuration()

    monkeypatch.setenv("INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET", "y" * 32)
    _validate_production_configuration()


def test_startup_does_not_auto_create_tables_for_non_sqlite(monkeypatch) -> None:
    from freellmpool.api import db as db_module

    monkeypatch.setattr(
        db_module, "DATABASE_URL", "postgresql://user:pass@localhost/production"
    )
    monkeypatch.delenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES", raising=False)
    assert db_module._auto_create_allowed() is False
    monkeypatch.setenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES", "1")
    assert db_module._auto_create_allowed() is True
    monkeypatch.setattr(
        db_module, "DATABASE_URL", "sqlite:///./industrial_rfq.db"
    )
    monkeypatch.delenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES", raising=False)
    assert db_module._auto_create_allowed() is True


def test_clarification_traceability_columns_are_migrated(tmp_path: Path) -> None:
    database = tmp_path / "clarification.db"
    _alembic("upgrade", "head", db_path=database)
    connection = sqlite3.connect(database)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(technical_clarifications)"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "rfq_revision_id",
        "requirement_id",
        "gap_type",
        "evaluated_offered",
        "evaluation_status",
        "evaluation_evidence",
    } <= columns

    connection = sqlite3.connect(database)
    try:
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(technical_clarifications)"
        ).fetchall()
    finally:
        connection.close()
    foreign_key_targets = {row[2] for row in foreign_keys}
    assert {"rfq_revisions", "requirements"} <= foreign_key_targets
