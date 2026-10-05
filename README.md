# Industrial RFQ Intelligence

> **SaaS transition:** the existing evidence-aware engineering core is being extended into a project-aware industrial procurement intelligence platform. See `docs/SAAS_PRODUCT_ARCHITECTURE.md`, `docs/SAAS_DATA_MODEL.md`, and `docs/SAAS_IMPLEMENTATION_ROADMAP.md` for the target architecture and staged build plan.

Evidence-aware technical and commercial review for industrial RFQs, vendor quotations, and EPC engineering workflows.

Industrial RFQ Intelligence is a Python-based engineering decision-support workflow that combines document extraction, LLM-assisted structured reading, deterministic compliance logic, and evidence traceability.

The first portfolio workflow targets:

**415 V Induction Motors & VFD Supply**

Given an RFQ/specification and 2–5 vendor quotations, the workflow can extract structured requirements and vendor data, normalize common engineering parameters, identify deviations, preserve quotation evidence, and produce a structured engineering review.

> **Important:** The LLM assists with extraction and grounded reading. It does **not** decide technical compliance. Compliance classification is performed by deterministic Python logic.

The deterministic layer now supports numeric equality plus `>=`, `<=`, `>`, `<`, inclusive numeric ranges (`400-450 V` / `400 to 450 V`), and percentage tolerances (`415 V ±5%` or `415 V +/-5%`) when units are compatible. Unsupported expressions fall back to normalized exact matching rather than being guessed.

## What this project demonstrates

- Industrial RFQ and quotation intelligence
- Engineering requirement extraction
- LLM-assisted grounded document reading
- Deterministic technical compliance evaluation
- Technical deviation detection
- Basic engineering-unit and parameter normalization
- Commercial-data structuring
- Evidence registers and claim-status tracking
- Universal document normalization through MarkItDown with source/page provenance
- Python CLI and reusable library architecture
- Automated testing and CI/CD-oriented project structure
- Engineering/EPC decision-support thinking

The design is intentionally aligned with real industrial workflows such as vendor technical-commercial evaluation, EPC procurement support, FAT/SAT documentation review, and automation-package engineering.

## Workflow

~~~text
RFQ / Specification
        │
        ▼
Document ingestion
        │
        ▼
LLM-assisted structured extraction
        │
        ▼
Normalization
        │
        ▼
Deterministic compliance engine
        │
        ├── COMPLIANT
        ├── DEVIATION
        └── UNVERIFIED
        │
        ▼
Evidence register
        │
        ▼
Engineering review report
~~~

## Evidence-first design

Important claims are associated with evidence and a claim status:

- \`VERIFIED\`
- \`PARTIALLY VERIFIED\`
- \`UNVERIFIED\`
- \`INFERENCE\`
- \`ASSUMPTION\`
- \`CONTRADICTED\`

The workflow is designed so that unsupported information remains visible for engineering review rather than silently becoming an accepted fact.

**Claim-status rule:** if `claim_status` is omitted from structured vendor or commercial input, it defaults to `UNVERIFIED`. A claim is `VERIFIED` only when the input explicitly marks it as verified; the built-in demo dataset uses explicit `VERIFIED` statuses. This prevents missing provenance metadata from being silently treated as verified evidence.
If an evidence field is omitted or empty, the claim is accepted structurally but is forced to `UNVERIFIED` and therefore requires review. The same rule applies to technical vendor claims and commercial claims.
If multiple quotation claims for the same vendor/parameter materially conflict, the compliance row is forced to `UNVERIFIED`, the claim status becomes `CONTRADICTED`, and the conflicting evidence/value references are retained for engineer review. A contradictory claim is never treated as compliant.

For document-based extraction, source and page markers are preserved so an extracted vendor value can be traced back to the originating document page.

## Example

The included sample demonstrates a two-vendor motor evaluation.

~~~bash
industrial-rfq-intelligence industrial-rfq \
  --input examples/industrial_rfq/sample_input.json \
  --markdown
~~~

The sample report contains:

- engineering requirements
- vendor-by-vendor compliance
- technical deviation identification
- commercial information
- evidence references
- engineer review actions
- workflow controls and limitations

A machine-readable JSON result is also supported:

~~~bash
industrial-rfq-intelligence industrial-rfq \
  --input examples/industrial_rfq/sample_input.json \
  --json
~~~

The current Python package/CLI namespace remains \`freellmpool\` for implementation compatibility while the repository and product are being separated from the original gateway identity. Package identity cleanup is tracked as a subsequent hardening milestone.

## LLM-assisted extraction

Raw RFQ and quotation text can be passed through the grounded extraction boundary:

~~~bash
industrial-rfq-intelligence industrial-rfq \
  --extract examples/industrial_rfq/raw_input.json
~~~

The extraction layer is constrained to explicitly stated engineering facts and evidence. It does not calculate compliance or make procurement decisions.

## Document ingestion

The canonical document-normalization layer uses Microsoft's MIT-licensed MarkItDown package to convert supported source documents into Markdown before engineering extraction. PDF pages are normalized independently so the resulting Markdown retains explicit page markers; TXT/Markdown, Word, PowerPoint, Excel, and image inputs can enter through the same normalization boundary.

~~~python
from freellmpool.document_normalizer import normalize_document

normalized = normalize_document("specification.pdf")
print(normalized.markdown)
~~~

The RFQ document-to-LLM ingestion path uses this Markdown normalization layer by default. MarkItDown handles the canonical document parsing/rendering, while sparse/scanned PDF pages and standalone document images automatically fall back to local Tesseract OCR. PDF page markers remain explicit, so OCR-derived claims retain page provenance. Install the package with the `ocr` dependencies and a Tesseract runtime in deployments that process scanned documents. The legacy page extractor remains available as an explicit compatibility fallback.

## Engineering report

The report renderer provides a recruiter- and engineer-readable Markdown output containing:

1. Executive summary
2. Technical compliance matrix
3. Commercial information
4. Evidence register
5. Engineer review actions
6. Controls and limitations

Example:

\`examples/industrial_rfq/sample_report.md\`

## What this is NOT

This project is not:

- an autonomous procurement system;
- an engineering certification or approval system;
- a PLC/DCS programming or control system;
- an unattended plant-operation system;
- a replacement for qualified engineering review;
- a system that should make production purchasing decisions without human approval.

Commercial information is presented for review. The current workflow deliberately does not rank vendors or select a procurement winner.

## Technical architecture

The implementation separates three responsibilities:

**AI / LLM layer**
- grounded reading
- extraction of explicitly stated facts
- structured output generation

**Deterministic engineering layer**
- schema validation
- parameter normalization
- unit normalization
- requirement/vendor comparison
- compliance classification

**Evidence/reporting layer**
- source and page provenance
- claim-status tracking
- review flags
- structured engineering report

This separation is central to the project's reliability model: generative output is not treated as the final engineering decision.

## Repository structure

~~~text
industrial-rfq-intelligence/
├── src/freellmpool/
│   ├── industrial.py
│   ├── industrial_report.py
│   └── ...
├── examples/
│   └── industrial_rfq/
├── tests/
├── docs/
├── industrial_demo.py
├── INDUSTRIAL_PRODUCT.md
└── pyproject.toml
~~~

## Current scope

Implemented:

- structured RFQ input validation
- vendor quotation data validation
- LLM-assisted grounded extraction
- commercial-field extraction
- engineering parameter aliases
- broader engineering-unit normalization (A/kA, Hz, rpm, Nm, °C, pressure, length, mass)
- deterministic compliance matrix
- evidence register
- PDF/TXT/Markdown text ingestion
- source/page provenance
- engineering Markdown report
- CLI JSON/Markdown output
- automated test and CI configuration

Planned product work includes table extraction, broader document coverage, richer reporting, expanded engineering validation, and reviewer-oriented workflow interfaces. Scanned-PDF OCR is implemented as an optional ingestion capability.

## Engineering context

The project is designed from an industrial automation/EPC perspective, where technical requirements, vendor offers, documentary evidence, commercial constraints, and human engineering review must remain distinguishable.

The portfolio use case is intentionally narrower than a generic AI assistant: it focuses on turning unstructured industrial procurement documents into traceable engineering decision-support data.

## Development

Python 3.11+.

Install development dependencies:

~~~bash
python -m pip install -e ".[dev]"
~~~

Run the test suite:

~~~bash
pytest
~~~

Run linting:

~~~bash
ruff check .
~~~

Run type checking:

~~~bash
mypy src
~~~

Actual local test execution should be treated separately from repository configuration; CI status should be verified from GitHub Actions for each pushed revision.

## License

MIT
