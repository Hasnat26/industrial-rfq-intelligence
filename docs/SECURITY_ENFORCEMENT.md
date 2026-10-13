# Security enforcement and merge-control evidence

This document describes the security controls for **Industrial RFQ Intelligence**.
It distinguishes automated checks from GitHub rules that make those checks
mandatory for merging.

## Automated validation

The repository currently defines these GitHub Actions workflows:

- `.github/workflows/ci.yml` — Python 3.11–3.14 lint, type checks, product
  tests, CLI smoke tests, PostgreSQL migration validation, container runtime
  smoke, and wheel/source-distribution smoke tests.
- `.github/workflows/security.yml` — high-severity Bandit source audit,
  Python dependency audit, GitHub Actions workflow audit with zizmor, Trivy
  container vulnerability audit, and security regression tests.
- `.github/workflows/codeql.yml` — CodeQL security-extended analysis for
  Python.

These workflows are configured to run on pull requests targeting `main` and
on pushes to `main` (with scheduled and manual triggers where configured).
A workflow definition or a successful run does **not** by itself prove that
GitHub blocks merges when a check fails.

## Live merge-control evidence

Last checked: **2026-10-13**.

- The GitHub branch metadata endpoint reported `main.protected = false`.
- The repository-level rulesets endpoint available to the connected integration
  returned an empty list.
- The classic branch-protection detail endpoint returned HTTP 403
  (`Resource not accessible by integration`), so its detailed settings could
  not be inspected.

Therefore, the effective merge requirements—including required status checks,
required review count, and any organization-level or inherited policy—are
**NOT VERIFIED** from the available integration evidence. Do not claim that
specific checks or a CodeQL ruleset are mandatory based on this document alone.
The previously documented ruleset ID and legacy `0xzr/freellmpool` API paths
are not evidence of current enforcement for this repository.

A repository administrator should verify the effective settings read-only in
GitHub or with an authorized CLI session before making any merge-enforcement
claim:

```bash
gh api repos/Hasnat26/industrial-rfq-intelligence/branches/main
gh api repos/Hasnat26/industrial-rfq-intelligence/branches/main/protection
gh api repos/Hasnat26/industrial-rfq-intelligence/rulesets
```

If access to the protection endpoint is denied, record the result as
**NOT VERIFIED** rather than inferring that no controls exist. Do not change
branch protection or rulesets merely to make a pull request mergeable.

## Review and release boundaries

- AI-assisted analysis is not independent human approval.
- No pull request may be merged without explicit product-owner authorization.
- A green repository CI run validates the tested commit only; it does not prove
  the deployed service is running that commit or that hosted tenant isolation,
  production database recovery, billing, or runtime security has passed.
- Hosted security tests, production test accounts, production data access, and
  production configuration changes require an explicitly approved safe scope.
- Keep procurement qualification deterministic and evidence-based. LLM
  extraction must not make compliance or award decisions, and no vendor emails
  or procurement awards may be triggered autonomously.

Update this document only when new live evidence confirms a change in the
effective controls. Include the check date and the exact verified configuration;
otherwise retain the **NOT VERIFIED** status.
