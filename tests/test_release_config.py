from __future__ import annotations

import tomllib
from pathlib import Path

from freellmpool import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_installed_package_version_matches_pyproject() -> None:
    """`_version.py` is documented as the single source for the package version."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"]


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
