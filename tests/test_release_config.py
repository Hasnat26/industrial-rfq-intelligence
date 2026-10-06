from __future__ import annotations

import tomllib
from pathlib import Path

from freellmpool import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_installed_package_version_matches_pyproject() -> None:
    """`_version.py` is documented as the single source for the package version."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"]


def test_api_and_release_docs_report_the_authoritative_version() -> None:
    """No current-facing artifact may contradict the package version."""
    from freellmpool.api.app import app

    assert app.version == __version__

    for doc in ("docs/index.html", "docs/AGENTS.md", "docs/INTEGRATIONS.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert f"Latest release: {__version__}" in text, doc
        assert "0.13.0" not in text, f"stale version in {doc}"

    index = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert f'"softwareVersion": "{__version__}"' in index

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog


def test_release_identity_is_industrial_rfq() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'name = "industrial-rfq-intelligence"' in pyproject
    assert 'industrial-rfq-intelligence = "freellmpool.cli:main"' in pyproject
    assert "Industrial RFQ Intelligence" in checklist
    assert "freellmpool" in checklist
    assert "OpenAI-compatible gateway" not in dockerfile
    assert "ghcr.io/0xzr/freellmpool" not in dockerfile


def test_release_checklist_forbids_unverified_ci_claims() -> None:
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "Do not state that a release is CI-verified" in checklist
    assert "P3-M14" in checklist
    assert "Only publish claims supported by" in checklist


def test_ci_checks_both_wheel_and_sdist_installation() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pip install dist/*.whl" in workflow
    assert "pip install dist/*.tar.gz" in workflow
    assert "industrial-rfq-intelligence --version" in workflow
    assert "industrial-sdist-report.md" in workflow


def test_saas_deployment_surface_is_explicit() -> None:
    dockerfile = (ROOT / "Dockerfile.saas").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.saas.yml").read_text(encoding="utf-8")
    deployment = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")

    assert 'CMD ["uvicorn", "freellmpool.api.app:app"' in dockerfile
    assert 'HEALTHCHECK' in dockerfile
    assert 'industrial-rfq-api:' in compose
    assert 'Dockerfile.saas' in compose
    assert 'INDUSTRIAL_RFQ_DATABASE_URL' in deployment
    assert 'alembic upgrade head' in deployment



def test_saas_compose_separates_local_smoke_from_production() -> None:
    local = (ROOT / "docker-compose.saas.yml").read_text(encoding="utf-8")
    production = (ROOT / "docker-compose.saas.production.yml").read_text(encoding="utf-8")

    assert "INDUSTRIAL_RFQ_ENV: development" in local
    assert "sqlite:////app/data/industrial_rfq.db" in local
    assert "INDUSTRIAL_RFQ_ENV: production" in production
    assert "INDUSTRIAL_RFQ_DATABASE_URL: ${INDUSTRIAL_RFQ_DATABASE_URL:?" in production
    assert "INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET: ${INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET:?" in production
    assert "INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET: ${INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET:?" in production
    assert "sqlite:" not in production
