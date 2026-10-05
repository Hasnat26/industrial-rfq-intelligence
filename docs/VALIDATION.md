# Validation Status

## Current CI validation scope

The active GitHub Actions CI workflow validates the Industrial RFQ product with:

- Ruff linting;
- strict mypy validation for the Industrial RFQ modules and API/domain packages;
- the full pytest suite;
- focused branch/line coverage for the active Industrial RFQ modules;
- package/wheel and sdist smoke testing;
- product-native CLI version smoke;
- industrial RFQ JSON CLI smoke; and
- industrial RFQ Markdown CLI smoke.

Separate security workflows provide Bandit, pip-audit, zizmor, Trivy, and CodeQL validation.

The legacy package-wide `scripts/check_coverage.py` gate is intentionally not part of the active CI contract. `tests/test_ci_config.py` explicitly prevents accidental reintroduction of that removed gate.

## Latest verified execution

The latest verified CI run is **Run #413**, for commit `8e9a1d4e35ed942cfb59516d5d9aea6c1db963bf`.

The run completed with conclusion **success** across Python 3.11, 3.12, 3.13, and 3.14. Each matrix job completed linting, type checking, CLI smoke, pytest, and build/wheel smoke successfully. The latest test execution reported **167 passed**.

This is execution evidence, not merely workflow configuration.

## Validation principle

**Configured is not passed. A green execution result is required before claiming a test or CI check passed.**

## Sample RFQ reproducibility

The active Industrial RFQ test suite loads `examples/industrial_rfq/sample_input.json`, renders the engineering report through the production renderer, and compares it byte-for-byte with `examples/industrial_rfq/sample_report.md`. This prevents the checked-in demonstration from drifting away from the actual deterministic workflow.

## Local execution limitation

The current working environment does not independently represent a complete local repository test run. GitHub Actions is therefore the authoritative execution evidence for the latest revision.
