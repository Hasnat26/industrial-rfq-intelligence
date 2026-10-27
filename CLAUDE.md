# Claude Code Guidelines

These guidelines reduce common coding mistakes. Apply them alongside the repository's `AGENTS.md`; do not bypass or weaken the existing metaswarm workflow, mandatory TDD, review gates, coverage thresholds, or declared file scope.

## 1. Think Before Coding

- State material assumptions and identify ambiguities before implementation.
- If multiple interpretations could change the result, present them and ask a focused question rather than guessing.
- Surface trade-offs and recommend a simpler alternative when appropriate.
- If blocked by uncertainty, explain what is unclear instead of proceeding silently.

## 2. Simplicity First

- Implement the minimum change that fully satisfies the request.
- Do not add unrequested features, speculative flexibility, or abstractions for one-off use.
- Follow established project patterns and quality requirements.
- Simplify code that is more complex than the problem requires.

## 3. Surgical Changes

- Change only files and behavior needed for the requested outcome.
- Do not refactor unrelated code, comments, formatting, or configuration.
- Preserve existing conventions and project-specific instructions.
- Report unrelated issues instead of fixing them without authorization.
- Remove only imports, variables, or functions made unused by your own changes.

## 4. Goal-Driven Execution

- Define observable success criteria for non-trivial work.
- For bug fixes, add or update a regression test that reproduces the issue before fixing it.
- For new behavior, add tests for expected and invalid cases as appropriate.
- For refactors, verify behavior with tests before and after.
- State a brief plan using `step → verification`, then run the available checks and report actual results.
- Never claim tests or checks passed unless they were executed and their results inspected.

## Project Workflow and Safety

- `AGENTS.md` remains authoritative for this repository's metaswarm orchestration, TDD, design/plan review gates, coverage requirements, and file-scope discipline. These guidelines supplement it; they do not replace it.
- Do not use `--no-verify` or force-push without explicit user approval.
- Do not overwrite existing user data or configuration without first inspecting it and obtaining approval where needed.
- Clearly distinguish verified facts, assumptions, and unverified results.

## How to Tell These Guidelines Are Working

- Diffs contain only changes required by the task.
- Clarifying questions precede consequential assumptions.
- Implementations avoid unnecessary complexity.
- Tests and quality gates are reported with evidence.
