from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_is_scoped_to_the_industrial_rfq_product() -> None:
    workflow = _workflow()

    assert workflow.count("\n  industrial:\n") == 1
    assert "pytest tests/test_industrial_demo.py tests/test_industrial_report.py" in workflow
    assert "freellmpool.industrial" in workflow
    assert "freellmpool.industrial_report" in workflow
    assert "industrial-rfq-intelligence industrial-rfq" in workflow


def test_ci_uses_supported_python_matrix() -> None:
    workflow = _workflow()
    match = re.search(r'python-version:\s*\[([^\]]+)\]', workflow)

    assert match is not None
    versions = re.findall(r'["\'](3\.\d+)["\']', match.group(1))
    assert versions == ["3.11", "3.12", "3.13", "3.14"]


def test_ci_has_no_removed_legacy_jobs_or_release_workflows() -> None:
    workflow = _workflow()
    workflows_dir = ROOT / ".github" / "workflows"

    assert "docker-smoke:" not in workflow
    assert "opencode-packages:" not in workflow
    assert "mcp-manifest:" not in workflow
    assert "publish-opencode.yml" not in workflow
    assert "publish-mcp.yml" not in workflow
    assert "publish-llm-plugin.yml" not in workflow

    workflow_names = {path.name for path in workflows_dir.glob("*.yml")}
    assert workflow_names == {"ci.yml", "codeql.yml", "security.yml"}


def test_ci_validates_active_product_surfaces() -> None:
    workflow = _workflow()

    for required in (
        "ruff check .",
        "mypy --follow-imports=skip src/freellmpool/industrial.py src/freellmpool/industrial_report.py",
        "industrial-rfq-intelligence --version",
        "industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --json",
        "industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --markdown",
        "pytest",
        "python -m build",
        "python -m twine check",
        "bandit --recursive src --severity-level high --confidence-level high --ignore-nosec",
        "python -m pip_audit . --strict",
        "zizmor --strict-collection --no-ignores --no-config --min-severity=high --min-confidence=high .",
    ):
        assert required in workflow


def test_ci_has_no_legacy_coverage_gate_contract() -> None:
    workflow = _workflow()

    assert "--cov=freellmpool --cov-branch" not in workflow
    assert "python scripts/check_coverage.py .coverage.json" not in workflow
    assert "docker/login-action" not in workflow
    assert "npm publish" not in workflow
