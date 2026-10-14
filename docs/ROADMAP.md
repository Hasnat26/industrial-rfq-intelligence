# Roadmap

Industrial RFQ Intelligence is an evidence-aware AI-assisted engineering decision-support system for industrial RFQs and vendor quotations.

## Product north star

**AI reads and structures. Deterministic logic compares. Evidence explains. Engineers decide.**

The system is designed around a concrete workflow:

RFQ/specification + vendor quotations → document ingestion → structured extraction → normalization → deterministic technical/commercial comparison → evidence register → engineering review report.

## Current scope

Implemented:

- structured Industrial RFQ input;
- vendor technical-value comparison;
- deterministic compliance operators, ranges, and percentage tolerances;
- engineering-unit normalization;
- missing-evidence fail-closed handling;
- conflicting-claim detection;
- commercial comparison;
- evidence register and review actions;
- PDF/TXT/Markdown document ingestion with provenance;
- LLM-assisted grounded extraction;
- Markdown/JSON engineering reports;
- native `industrial-rfq-intelligence` CLI.

## Next product work

1. Higher-quality table/document extraction.
2. OCR for scanned RFQs and quotations.
3. More engineering domains and parameter semantics.
4. Stronger provenance at page/table/cell level.
5. Structured commercial-risk and exception reporting.
6. Reviewer-oriented web/API workflow.
7. Benchmark datasets for evidence-aware RFQ extraction and comparison.

## Explicit non-goals

The product will not become:

- an autonomous purchasing agent;
- a PLC/DCS programming agent;
- a plant-control execution system;
- an unattended vendor-selection system;
- a system that presents inferred claims as verified evidence.

The legacy `freellmpool` runtime modules remain in the repository only where needed for implementation compatibility. They are not the product roadmap.

## Master milestone: P3-M14 → P3-M28 — Production Readiness

The next phase is tracked as one master milestone with sequential sub-milestones. Each sub-milestone should be completed and reported before starting the next.

### P3-M14 — CI execution evidence — DONE
- [x] Determine why GitHub Actions reports zero workflow runs. *(Resolved: the "zero runs" observation was stale. CI executes on push/PR.)*
- [x] Confirm workflow execution on push/PR. *(main CI Run #653 `38288890112` green on `f363adc5`; per-PR runs green.)*
- [x] Capture the first real green run before claiming CI success. *(Run #653 — all five jobs pass: Python 3.11–3.14 + postgres-migrations.)*

### P3-M15 — CI/test configuration reconciliation — DONE
- [x] Audit stale tests asserting deleted legacy workflows. *(Found `tests/test_supply_chain.py`: 10/25 failing, excluded from `testpaths`, asserting deleted `docker.yml`/`promote-latest.yml`/`release-evidence.yml` and the old `0xzr/freellmpool` identity.)*
- [x] Remove, rewrite, or quarantine obsolete assertions. *(Removed the 8 dead legacy docker/release/`0xzr`-checklist assertions; ported the still-active coverage — repo-wide action commit-pinning, Dockerfile digest pinning, PR security gates, and `scripts/security_exceptions.py` fail-closed policy validation — into the collected `tests/test_security_config.py`, with the two stale `0xzr/freellmpool` issue-URL fixtures corrected to the current repository.)*
- [x] Ensure active product validation cannot be masked by stale tests. *(Active security-exception + action-pinning validation now runs inside the `pytest` gate; the misleading excluded failing suite is gone.)*

### P3-M16 — Industrial core API cleanup — DONE
- [x] Audit legacy `freellmpool` identity leakage from product-facing output/API. *(Product-facing surfaces return the industrial identity, e.g. `build_report` reports `product: industrial-rfq-intelligence`; the remaining leakage was stale test fixtures pointing at `0xzr/freellmpool`, removed in P3-M15.)*
- [x] Replace misleading legacy product strings where safe.
- [x] Preserve the compatibility namespace only where required and documented. *(The `freellmpool` Python package namespace is retained deliberately as the documented compatibility namespace — see "Explicit non-goals"; it is not product roadmap surface.)*

### P3-M17 — Input/schema contract hardening — DONE
- [x] Define a versioned Industrial RFQ input schema. *(`docs/RFQ_INPUT_SCHEMA.md`, current version `1.0`; `RFQ_SCHEMA_VERSION` in `src/freellmpool/industrial.py`.)*
- [x] Harden type/required-field validation. *(`load_rfq_input` fails closed with `ValueError` on malformed JSON, wrong types, empty required collections, duplicate requirement tags, invalid claim statuses, unsupported versions.)*
- [x] Add duplicate, malformed-value, and compatibility cases.
- [x] Document schema compatibility expectations. *(Missing `schema_version` is treated as `1.0`; unsupported versions rejected — documented in the schema doc.)*

### P3-M18 — Evidence/provenance hardening — DONE
- [x] Standardize source/page/section/table/cell provenance. *(`docs/EVIDENCE_POLICY.md`; structured provenance carried end-to-end, including table/cell — see `examples/industrial_rfq/benchmark.json` TABLE-03.)*
- [x] Require explicit evidence for VERIFIED claims. *(`load_rfq_input` rejects VERIFIED claims without provenance — covered by `tests/test_security_config.py::test_verified_commercial_claim_requires_provenance` and the LLM-boundary test.)*
- [x] Add provenance fixtures and regression tests.
- [x] Preserve contradiction/review states end-to-end. *(CON-05 benchmark case → `CONTRADICTED`/`UNVERIFIED`; contradictory claims are never silently resolved.)*

### P3-M19 — Engineering comparison expansion — DONE
- [x] Add parameter-specific engineering semantics.
- [x] Expand industrial unit coverage deliberately.
- [x] Add boundary, range, tolerance, and incompatible-dimension tests.
- [x] Keep unsupported semantics fail-closed.

### P3-M20 — Commercial/risk review layer — DONE
- [x] Normalize commercial fields.
- [x] Add delivery/warranty/payment exception flags.
- [x] Add evidence-aware commercial risk reporting.
- [x] Do not introduce supplier ranking or winner selection.

### P3-M21 — Document intelligence benchmark — DONE
- [x] Build a representative RFQ/quotation benchmark.
- [x] Include text, PDF, table-heavy, ambiguous, and contradictory cases.
- [x] Define extraction, provenance, and compliance metrics.
- [x] Separate LLM extraction quality from deterministic comparison quality.

### P3-M22 — Report quality and auditability — DONE
- [x] Add deterministic commercial-risk review to the human-readable report.
- [x] Preserve commercial provenance in the evidence register.
- [x] Add report auditability regression coverage.
- [x] Refresh the checked-in Markdown report fixture.

### P3-M23 — Reviewer workflow interface — DONE
- [x] Design UPLOAD → EXTRACTION → REVIEW → REPORT states.
- [x] Define a local/API-neutral reviewer workflow contract.
- [x] Require explicit human approval before REPORT.
- [x] Exclude production credentials, autonomous procurement actions and unattended approval.

### P3-M24 — Repository/public-surface cleanup — DONE
- [x] Audit legacy gateway/provider/MCP/SEO documentation, HTML, issue templates, scripts and assets.
- [x] Remove obsolete legacy public material from the repository surface.
- [x] Remove stale demo/social-preview/tokenmax binary assets tied to the legacy surface.
- [x] Recheck the primary README/product documentation surface; retained `freellmpool` only where required for implementation compatibility.

### P3-M25 — Security/dependency gate — DONE
- [x] Verify and enforce Bandit, pip-audit, zizmor and container security workflows.
- [x] Review dependency and supply-chain controls: weekly Dependabot coverage for pip, GitHub Actions and Docker; commit-pinned workflow actions; bounded security-exception registry.
- [x] Add security regression cases for document ingestion, prompt-like untrusted text, unsupported active content types and evidence/provenance boundaries.

### P3-M26 — Packaging/release readiness — DONE
- [x] CI now builds and smoke-installs both wheel and sdist artifacts, including the native Industrial RFQ CLI.
- [x] Replaced the legacy gateway container identity with an Industrial RFQ CLI container definition.
- [x] Replaced the stale release checklist and removed obsolete coverage/release instructions.
- [x] Added packaging/release regression tests and an evidence-based release checklist.
- [x] Release claims explicitly require executable, reproducible, checked-in, or directly inspectable evidence.

### P3-M27 — Portfolio/recruiter evidence pack — DONE
- [x] Created a concise architecture/evidence page at `docs/PORTFOLIO_EVIDENCE.md`.
- [x] Added a reproducible end-to-end demo path at `examples/industrial_rfq/DEMO.md`.
- [x] Documented the engineering problem, deterministic controls, evidence policy, human-review boundary, and limitations.
- [x] Tied portfolio claims to inspectable repository artifacts and explicitly separated configuration evidence from execution evidence.
- [x] Kept the unresolved P3-M14 CI execution-evidence gap visible rather than claiming CI success.

### P3-M28 — Final acceptance gate
- [x] Real CI green-run evidence — main CI Run #653 (`38288890112`) passed all five jobs (Python 3.11–3.14 + postgres-migrations) on current main `f363adc562a494de57cca58c530c99afdfba2818`. The earlier "GitHub reports `total_count: 0` workflow runs" observation is stale and retracted: CI now executes and passes on every push/PR.
- [x] Benchmark acceptance artifacts are present and mapped in `docs/FINAL_ACCEPTANCE.md`.
- [x] Security gate configuration and regression artifacts are present and mapped in `docs/FINAL_ACCEPTANCE.md`.
- [x] Package/CLI smoke configuration is present and mapped in `docs/FINAL_ACCEPTANCE.md`.
- [x] Sample report and consistency regression artifacts are present and mapped in `docs/FINAL_ACCEPTANCE.md`.
- [x] Public documentation audit completed.
- [ ] Final release/portfolio readiness review — no longer blocked on CI evidence (P3-M14 is DONE); remains open pending the owner-gated live acceptance gates in `docs/LAUNCH_ACCEPTANCE_MATRIX.md` (durable database/recovery, production migration baseline/configuration, billing provider validation, authenticated tenant-isolation smoke).

Acceptance evidence record: `docs/FINAL_ACCEPTANCE.md`.

### Phase non-goals

This phase will not add:
- autonomous purchasing;
- vendor winner/ranking automation;
- PLC/DCS control execution;
- inferred claims presented as VERIFIED;
- production deployment or production credentials.

Current status: P3-M1 through P3-M27 complete. P3-M28's CI green-run evidence is satisfied (main CI Run #653 `38288890112` green on `f363adc`); its final release/portfolio readiness review remains open pending the owner-gated live acceptance gates. Main CI green is claimed with linked evidence; hosted production readiness is not.

