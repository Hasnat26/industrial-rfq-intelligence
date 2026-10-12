# Customer Pilot Onboarding — Industrial RFQ Intelligence

**Pilot workflow:** 415 V, three-phase induction-motor RFQ review  
**Audience:** customer engineering and procurement reviewers  
**Scope:** repository-local CLI quickstart using the checked-in structured example. This is not a claim that the hosted service has passed customer acceptance.

## 1. Before you start

You need Python 3.11 or later and a terminal. The structured example uses synthetic data and **does not require an LLM provider key or make provider calls**. Do not put customer quotations, credentials, or confidential specifications in a public repository.

Clone the repository and enter its directory:

```bash
git clone https://github.com/Hasnat26/industrial-rfq-intelligence.git
cd industrial-rfq-intelligence
```

From the repository root, create a virtual environment:

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the project:

```bash
python -m pip install -e .
```

The CLI requires Python 3.11+. Run the commands below from the repository root so the example paths resolve.

## 2. Safe first run: structured input

Generate both report formats from the existing sample:

```bash
industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --markdown --output pilot-report.md
industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --output pilot-report.json
```

The command prints a confirmation for each output file. The Markdown report is intended for reviewer reading; the JSON report is the machine-readable result. The checked-in [sample report](../examples/industrial_rfq/sample_report.md) is an **illustrative snapshot**, not proof that a customer document was processed during this task.

Inspect the report before sharing it. Confirm that requirement tags, offered values, status, evidence references, commercial terms, and review actions match the input. Do not treat a sample's `VERIFIED` label or placeholder page reference as verification of a real quotation.

## 3. Synthetic RFQ walkthrough

Use the existing files; do not create a second copy of the sample package:

- Structured input: `examples/industrial_rfq/sample_input.json`
- Optional raw-text extraction input: `examples/industrial_rfq/raw_input.json`
- Illustrative report: `examples/industrial_rfq/sample_report.md`
- Input contract: `docs/RFQ_INPUT_SCHEMA.md`

All vendor names, values, and quotation-page references in this demo are fictional placeholders. The main-branch demo does not include the underlying vendor quotation files.

The structured example contains four requirements:

| Tag | Requirement | Required value |
|---|---|---|
| R-01 | Rated voltage | 415 V |
| R-02 | Motor power | 75 kW |
| R-03 | Efficiency class | IE3 |
| R-04 | Ingress protection | IP55 |

The example compares Vendor A (USD 10,000; 8-week lead time; 24-month warranty) with Vendor B (USD 9,200; 12-week lead time; 12-month warranty). Vendor B offers IE2 against the IE3 requirement, so the report identifies a technical deviation despite its lower illustrative price. Payment terms also differ. **The software does not automatically select a supplier.**

For an actual pilot, replace the demo data with a customer-approved RFQ and quotations in a controlled working copy. Preserve the customer's requirement identifiers and record source filename/page/section for every claim. Review technical deviations, contradictory claims, missing evidence, currency, delivery, warranty, and payment terms with the authorized engineer/procurement reviewer. Record the reviewer's name, date, disposition, and unresolved clarifications outside the sample dataset. Do not mark a claim verified unless the underlying source has been checked.

### Optional document normalization and LLM-assisted extraction

The local document command can normalize a supported file to Markdown for manual review:

```bash
industrial-rfq-intelligence industrial-document path/to/specification.pdf > specification.md
```

Normalization is a separate step; it does **not** automatically turn multiple files into the structured input or run the full comparison. A person must inspect the normalized text and prepare/validate the schema in `docs/RFQ_INPUT_SCHEMA.md`.

The repository also provides an optional provider-dependent extraction workflow:

```bash
industrial-rfq-intelligence industrial-rfq --extract examples/industrial_rfq/raw_input.json --markdown --output extracted-report.md
```

This path uses a configured model provider and may send the supplied RFQ/quotation text outside the local environment under that provider's terms. It is not needed for the safe first run. Before using it with customer information, obtain customer approval and confirm the configured provider's data-handling, retention, residency, and commercial terms. Never commit API keys.

## 4. What the report means

Review these sections separately:

- **Technical compliance matrix:** requirement-by-requirement status and evidence. A deviation or `UNVERIFIED` claim needs engineering attention.
- **Commercial information / risk review:** price, currency, lead time, warranty, payment terms, and deterministic review flags where supplied. These fields are not a procurement decision.
- **Evidence register:** source references and claim status. Confirm each reference against the original customer document.
- **Engineer review actions:** the follow-up list; resolve or explicitly accept each item before the customer makes a decision.

The engine calculates deterministic comparison statuses from structured claims. It does not certify equipment, approve deviations, negotiate with suppliers, or authorize a purchase. The customer's authorized reviewers retain those responsibilities.

## 5. Supported inputs and known limitations

- **Structured CLI input:** JSON schema version 1.0; `requirements` and `vendor_data` are required non-empty arrays. See `docs/RFQ_INPUT_SCHEMA.md`. Evidence can be omitted by the schema, but missing evidence forces a claim to `UNVERIFIED`.
- **Local document normalization:** the configured MarkItDown dependencies cover PDF, TXT, Markdown, DOCX, PPTX, and XLSX inputs; common image formats can use the local OCR path. PDF pages retain page markers. Actual parsing/OCR quality depends on file content, installed parsers, OCR packages, and Tesseract language data; validate each format on a non-sensitive sample before the pilot.
- **Hosted API uploads:** the current batch-quotation upload route accepts PDF, TXT, and Markdown files, with a 10 MB maximum per file. This is distinct from the broader local normalization path.
- **Manual handoff:** document normalization, claim validation, structured JSON creation, comparison, and human review are separate steps. Do not assume that dropping a folder of files automatically produces an accepted report.
- **Retention:** the current application stores extracted text/pages and provenance, not a durable archive of original binary uploads. Keep originals in the customer's approved document system and apply its access/retention rules.
- **Provider dependency:** the structured `--input` demo is provider-independent. `--extract` requires a configured provider and has provider-specific availability, privacy, and cost implications.
- **Hosted acceptance:** a successful local CLI run or repository CI does not prove that a deployed environment is ready. The hosted authenticated workflow and cross-tenant isolation require separate owner-approved tests; they are not verified by this quickstart.
- **Human approval:** no report should be used as a purchase recommendation until qualified reviewers have checked source evidence, deviations, unverified claims, and commercial terms.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| `industrial-rfq-intelligence` not found | Activate the virtual environment and rerun `python -m pip install -e .` from the repository root. |
| Input file cannot be read | Check the working directory and relative path; use a copy of the checked-in example first. |
| Invalid RFQ JSON | Validate the JSON object and schema v1.0; requirement tags must be unique and required fields must be strings. |
| Provider/configuration error with `--extract` | Return to the structured `--input` workflow. Configure a provider only through the approved secret-management process; never paste a key into a ticket or commit it. |
| OCR text is missing or poor | Confirm that the file is readable and, for scanned content, that OCR dependencies and the Tesseract language data are installed. Have a person compare extracted text with the original. |
| A claim is `UNVERIFIED` or contradictory | Check the source and evidence reference; correct the input or request clarification. Do not change a status merely to make the report pass. |

## 7. Pilot acceptance checklist

Record the pilot ID, repository/application commit, input-file identifiers, report filenames, reviewer, date, evidence location, and final result. For every row, use **PASS** only when the stated evidence is retained; otherwise use **NOT VERIFIED**.

| Step | Acceptance test | Evidence to retain | Result |
|---|---|---|---|
| 1. Environment | Install on a clean Python 3.11+ environment and run the structured demo | Python version, install command/result, commit SHA | NOT VERIFIED until run |
| 2. Repeatability | Run both report commands twice against the same unchanged input | Both outputs and a recorded comparison; investigate and document any differences | NOT VERIFIED until run |
| 3. Requirements | Confirm R-01 through R-04 appear with the expected required values | Input and report excerpts | NOT VERIFIED until reviewed |
| 4. Deviation | Confirm Vendor B's IE2/IE3 mismatch is shown as a deviation | Technical matrix row and reviewer confirmation | NOT VERIFIED until reviewed |
| 5. Commercial review | Confirm price, currency, lead time, warranty, and payment terms are presented separately from technical status | Report excerpt plus commercial reviewer confirmation | NOT VERIFIED until reviewed |
| 6. Evidence traceability | Verify each real claim against the actual source document and page; reject placeholder demo evidence as customer evidence | Source-to-claim review log | NOT VERIFIED until reviewed |
| 7. Human disposition | Qualified reviewer records deviation disposition, clarifications, and procurement decision separately | Dated sign-off or controlled review record | NOT VERIFIED until signed |
| 8. Data handling | Confirm provider approval if `--extract` is used and originals are retained in the approved customer system | Data-handling approval and storage reference | NOT VERIFIED until confirmed |
| 9. Hosted workflow (if in scope) | Execute authenticated end-to-end and cross-tenant negative tests against the intended deployment | Deployment SHA, test-account IDs (no passwords), request/result evidence | NOT VERIFIED; separate gate |

**Pilot exit rule:** steps 1–7 must pass for the agreed sample/customer dataset. Steps 8–9 must also pass whenever their conditions apply. A local demo pass is not hosted acceptance, and a lower price does not override a technical deviation or reviewer decision.
