# Security enforcement and merge-control evidence

This document describes the security controls for **Industrial RFQ Intelligence**.
It distinguishes automated checks from GitHub rules that make those checks
mandatory for merging.

## Automated validation

The repository currently defines these GitHub Actions workflows:

- `.github/workflows/ci.yml` — Python 3.11–3.14 lint, type checks, product
  tests, CLI smoke tests, PostgreSQL migration validation, container runtime
  smoke, and wheel/source-distribution smoke tests. Its `Security gate` step
  runs Bandit, pip-audit, and zizmor as part of the `industrial` matrix job,
  and it builds and smoke-tests the SaaS container; that is not the same as
  the Trivy container vulnerability audit.
- `.github/workflows/security.yml` — `High-severity Python source audit`
  (Bandit), `Python dependency audit`, `GitHub Actions audit` (zizmor), and
  `Container vulnerability audit` (Trivy).
- `.github/workflows/codeql.yml` — `Analyze Python` security-extended analysis.

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
REPO=Hasnat26/industrial-rfq-intelligence

gh api "repos/$REPO/branches/main/protection/required_status_checks" \
  --jq '{strict, contexts}'
gh api "repos/$REPO/rulesets" \
  --jq '.[] | {id, name, target, enforcement, source}'
gh api "repos/$REPO/rules/branches/main"
```

These commands must be run with an identity authorized to read the relevant
settings. An authorization error or an empty result is not proof that all
other applicable restrictions are absent. Compare required context names with
the check runs for the exact pull-request head. After changing workflow job
names, update any verified required-check configuration through the approved
repository governance process; never remove a required context merely to
unblock a merge. Review CodeQL alerts using the applicable GitHub
code-scanning workflow and record the rationale for any reviewed false
positives.

If access to the protection endpoint is denied, record the result as
**NOT VERIFIED** rather than inferring that no controls exist. Do not change
branch protection or rulesets merely to make a pull request mergeable.

## Runtime security boundaries

- `/dashboard` and `/playground` are public only as a self-contained, data-free
  browser shell. Usage, provider inventory, ready models, and battle requests
  stay behind bearer-header authentication when proxy auth is configured.
  After form submission the token input is cleared and the token remains only
  in a JavaScript closure. It is never copied into a URL, cookie, Web Storage,
  rendered DOM, global, log, or HTML response, and a reload requires re-entry.
- `freellmpool local discover` probes only the fixed LM Studio, Ollama, and
  llama.cpp literal-loopback endpoints, or one explicit canonical
  literal-loopback URL. Requests have strict time/body/model bounds, send no
  credentials, and follow no redirects. Discovery never performs DNS, LAN, or
  process scanning. Import requires `--yes`, creates pin-only routes, and is
  reversible with `local remove --yes`.
- Streaming failover stops at downstream commit. Text-only Responses and
  Anthropic Messages content is delivered incrementally; tool and rich-content
  translation remains buffered. A post-commit upstream failure is never
  retried elsewhere and never ends with a successful terminal event.
- `freellmpool doctor` reports strict config syntax/table errors with sanitized
  line, column, and type metadata. It does not echo malformed values, API keys,
  bearer tokens, or other configuration secrets.

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
