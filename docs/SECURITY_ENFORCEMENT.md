# Security enforcement

## Repository merge controls

Security workflow definitions and GitHub-enforced merge requirements are separate things. The workflows currently define these jobs:

- `.github/workflows/security.yml`: `High-severity Python source audit`, `Python dependency audit`, `GitHub Actions audit`, and `Container vulnerability audit`.
- `.github/workflows/codeql.yml`: `Analyze Python`.
- `.github/workflows/ci.yml`: the `Security gate` step runs Bandit, pip-audit, and zizmor as part of the `industrial` matrix job. It also builds and smoke-tests the SaaS container; that is not the same as the Trivy container vulnerability audit.

The workflow files trigger on pull requests targeting `main`, but a workflow or job existing in the repository does not by itself make it a mandatory merge check. Before relying on a required status check or CodeQL ruleset, verify the effective GitHub settings for this repository. This document does not assert that any particular context is required or that a particular ruleset ID is active; those settings must be confirmed from live repository policy.

Administrators can inspect the repository's current controls without changing them:

```bash
REPO=Hasnat26/industrial-rfq-intelligence

gh api "repos/$REPO/branches/main/protection/required_status_checks" \
  --jq '{strict, contexts}'
gh api "repos/$REPO/rulesets" \
  --jq '.[] | {id, name, target, enforcement, source}'
gh api "repos/$REPO/rules/branches/main"
```

These commands must be run with an identity authorized to read the relevant settings. An authorization error or an empty result is not proof that all other applicable restrictions are absent. Compare required context names with the check runs for the exact pull-request head. After changing workflow job names, update any verified required-check configuration through the approved repository governance process; never remove a required context merely to unblock a merge. Review CodeQL alerts using the applicable GitHub code-scanning workflow and record the rationale for any reviewed false positives.

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
