# End-to-End Portfolio Demo

All examples in this directory are **synthetic demonstration data**. Vendor names, identifiers, dates, prices, and quotation terms are fictional and are not real offers or customer data.

## 1. Deterministic structured-input demo

Run the checked-in sample from the repository root:

```bash
python -m pip install -e ".[dev]"
industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --markdown > /tmp/industrial-rfq-report.md
industrial-rfq-intelligence industrial-rfq --input examples/industrial_rfq/sample_input.json --json > /tmp/industrial-rfq-report.json
```

The sample demonstrates requirements, vendor comparison, engineering deviation detection, commercial fields, evidence/provenance, and human review boundaries. Vendor A uses an equivalent 0.415 kV representation for the 415 V requirement. Vendor B intentionally contains an IE2 efficiency-class deviation against the IE3 requirement. The workflow reports the difference but does not choose a supplier.

## 2. Synthetic source-document pilot package

Source documents are under `examples/industrial_rfq/source_documents/`:

- `rfq_specification.md` — synthetic RFQ SYN-RFQ-415V-001 and requirements R-01 through R-04.
- `quotation_asterion_motor_works.md` — fictional Vendor A offer, quotation references Q-A-01 through Q-A-08.
- `quotation_bluehaven_electromechanical.md` — fictional Vendor B offer, quotation references Q-B-01 through Q-B-08, including the intentional IE2-versus-IE3 deviation.

These are Markdown source documents, a format supported by the existing document normalizer. Normalize and inspect each source document:

```bash
industrial-rfq-intelligence industrial-document examples/industrial_rfq/source_documents/rfq_specification.md > /tmp/pilot-rfq.md
industrial-rfq-intelligence industrial-document examples/industrial_rfq/source_documents/quotation_asterion_motor_works.md > /tmp/pilot-quote-a.md
industrial-rfq-intelligence industrial-document examples/industrial_rfq/source_documents/quotation_bluehaven_electromechanical.md > /tmp/pilot-quote-b.md
```

The existing interfaces do not automatically combine several normalized documents into the RFQ extraction command. For this example, `raw_input.json` is the explicit text handoff: its RFQ and quotation text should be checked against the normalized source documents and updated manually if the source documents change. It preserves the source quotation references in the text supplied to extraction.

With a model provider configured through the normal FreeLLMPool configuration, run the existing LLM-assisted extraction and deterministic review:

```bash
industrial-rfq-intelligence industrial-rfq --extract examples/industrial_rfq/raw_input.json --json > /tmp/pilot-review.json
industrial-rfq-intelligence industrial-rfq --extract examples/industrial_rfq/raw_input.json --markdown > /tmp/pilot-review.md
```

Each `--extract` invocation performs a separate model extraction and may consume provider quota; inspect the output rather than treating extraction as ground truth. The deterministic `--input sample_input.json` path above does not require a model provider. The source-document path is a human-reviewed normalization/transcription handoff, not automated document-to-evaluation orchestration.

Review the result for requirement R-03: the fictional Bluehaven offer states IE2 against IE3 required and should be surfaced as a deviation. Confirm the evidence register retains the Q-A/Q-B quotation references where the extractor provides them. The report is decision support only; an authorized engineer remains responsible for technical acceptance and procurement decisions. No supplier is automatically selected.

## Supported document boundary

The current `industrial-document` command normalizes supported local documents to Markdown with source metadata. This demo uses Markdown files. OCR is not needed for these text documents; do not infer OCR success or scanned-PDF support from this example. The document-normalization command does not itself run RFQ extraction or create the structured extraction handoff.

The portfolio boundary is: document normalization -> human-checked text handoff -> LLM-assisted extraction -> deterministic comparison -> evidence register -> human engineering review.
