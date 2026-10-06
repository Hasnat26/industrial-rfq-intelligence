# Industrial RFQ Intelligence — Product Specification

## 1. Product purpose

Industrial RFQ Intelligence is an evidence-aware engineering decision-support system for reviewing industrial RFQs, specifications, and vendor quotations.

The current product scope focuses on:

**415 V Induction Motors & VFD Supply**

The system converts engineering requirements and vendor offers into structured, traceable review data. It combines LLM-assisted document reading with deterministic engineering comparison logic so that generated text is not treated as the final compliance decision.

The intended users are engineers, project managers, EPC teams, procurement/technical-commercial reviewers, and engineering organizations handling repetitive vendor-document analysis.

## 2. Core problem

Industrial RFQ review often requires engineers to manually:

1. read long specifications;
2. identify mandatory technical requirements;
3. inspect multiple vendor quotations;
4. normalize different parameter names and units;
5. identify deviations and missing information;
6. trace each offered value back to documentary evidence;
7. prepare a review report for technical and commercial stakeholders.

The product is designed to reduce this document-review workload while keeping engineering judgement and approval with qualified human reviewers.

## 3. Current v1 workflow

~~~text
RFQ / Specification + Vendor Quotations
                    │
                    ▼
             Document ingestion
                    │
                    ▼
       LLM-assisted grounded extraction
                    │
                    ▼
          Schema validation / parsing
                    │
                    ▼
       Parameter and unit normalization
                    │
                    ▼
        Deterministic compliance engine
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
      COMPLIANT  DEVIATION  UNVERIFIED
                    │
                    ▼
             Evidence register
                    │
                    ▼
          Engineering review report
                    │
                    ▼
             Human engineer review
~~~

## 4. Inputs

### 4.1 RFQ / specification

The RFQ input contains explicit engineering requirements such as:

- equipment/tag identifier;
- parameter name;
- required value;
- engineering unit where applicable;
- requirement evidence/source.

### 4.2 Vendor quotations

Each vendor response may contain:

- vendor name;
- offered parameter;
- offered value;
- quotation evidence;
- claim status.

### 4.3 Commercial information

The current schema can represent:

- vendor;
- price;
- currency;
- lead time;
- warranty;
- payment terms;
- evidence;
- claim status.

Commercial data is presented as review information. It is not converted into an autonomous purchasing decision.

## 5. Processing model

### 5.1 Document ingestion

Supported document formats in the current implementation:

- PDF;
- TXT;
- Markdown.

PDF pages are extracted separately and represented with source/page provenance.

Scanned or image-only PDF OCR is available through the optional `ocr` dependency set and Tesseract runtime.

### 5.2 LLM-assisted extraction

The LLM is used as an extraction assistant.

Its responsibilities are limited to:

- reading supplied RFQ/quotation text;
- extracting explicitly stated engineering facts;
- returning structured fields;
- preserving evidence references.

The LLM must not:

- invent missing values;
- silently infer unstated specifications;
- calculate compliance;
- select a preferred vendor;
- make an unattended procurement decision.

### 5.3 Deterministic engineering engine

The deterministic Python layer performs:

- schema validation;
- parameter alias normalization;
- basic engineering-unit normalization;
- requirement/vendor matching;
- compliance classification;
- evidence-register generation;
- review-flag generation.

Current compliance outcomes are:

- COMPLIANT
- DEVIATION
- UNVERIFIED

The deterministic comparison engine supports numeric equality, relational operators (`>=`, `<=`, `>`, `<`), inclusive numeric ranges, and percentage tolerances when compatible engineering units are available. Unsupported expressions fall back to normalized exact matching; the engine does not infer unsupported engineering semantics.

## 6. Evidence and claim policy

The product uses the following claim-status vocabulary:

- VERIFIED
- PARTIALLY VERIFIED
- UNVERIFIED
- INFERENCE
- ASSUMPTION
- CONTRADICTED

Evidence is treated as a first-class data element.

A reviewable claim should retain:

- source type;
- vendor where applicable;
- field;
- value;
- evidence;
- claim status;
- whether engineering review is required.

The system is designed to keep unsupported or uncertain information visible rather than silently converting it into accepted engineering facts.

**Default rule:** when `claim_status` is omitted from vendor or commercial input, the implementation assigns `UNVERIFIED`. `VERIFIED` must be explicitly supplied by the input/extraction layer when the evidence supports that status. Built-in demonstration records use explicit `VERIFIED` values.
If evidence is omitted or empty, the claim is forced to `UNVERIFIED` and flagged for engineering review. Missing evidence never becomes verified merely because a value or status was supplied.
If multiple claims for the same vendor and normalized parameter materially disagree, the compliance result is `UNVERIFIED` with claim status `CONTRADICTED`. The conflicting values and evidence references are retained so an engineer can resolve the source discrepancy. Contradictory claims are never treated as compliant.

## 7. Output

The current product can generate:

### Technical compliance matrix

Requirement-by-requirement comparison of vendor offers.

### Commercial comparison

Structured commercial information for engineering/commercial review.

### Evidence register

Traceable record of technical and commercial claims and their supporting evidence/status.

### Engineer review actions

Items requiring attention because information is missing, uncertain, contradictory, or otherwise not fully verified.

### Markdown engineering report

A consolidated report containing:

1. executive summary;
2. technical compliance matrix;
3. commercial information;
4. evidence register;
5. engineer review actions;
6. controls and limitations.

JSON output is also supported for machine-readable workflows.

## 8. Human-in-the-loop control

The product is explicitly designed as decision support.

The final engineering decision remains with the responsible engineer/project/procurement organization.

The current implementation deliberately does not:

- automatically award a purchase;
- rank vendors as a procurement winner;
- approve technical deviations;
- certify engineering compliance;
- modify plant-control logic.

## 9. Reliability model

The architecture separates generative and deterministic responsibilities:

| Layer | Responsibility | Decision authority |
|---|---|---|
| LLM | Grounded reading and extraction | None |
| Validation | Schema/data integrity | None |
| Normalization | Parameter/unit representation | Deterministic |
| Compliance engine | Requirement vs. offer comparison | Deterministic |
| Evidence layer | Traceability and review flags | Deterministic |
| Human reviewer | Engineering interpretation and final decision | Final authority |

This separation is a core product principle.

## 10. Security and operational boundaries

The repository must not contain:

- production credentials;
- vendor confidential documents unless intentionally provided for development;
- plant-control credentials;
- secrets or API keys.

The repository now contains a database-backed, authenticated multi-tenant SaaS/API layer with workflow controls. Production deployment, provider-specific billing execution, granular RBAC, object storage, and enterprise operational hardening remain release-scope work.

## 11. Current implementation status

Implemented in the current repository:

- structured RFQ input loading;
- strict input validation;
- vendor quotation data validation;
- LLM-assisted grounded extraction;
- commercial-value extraction;
- parameter alias normalization;
- broader engineering-unit normalization (current, frequency, speed, torque, temperature, pressure, length, and mass);
- engineering operators, ranges, and percentage tolerances;
- deterministic compliance matrix;
- evidence register;
- review flags;
- PDF/TXT/Markdown ingestion;
- optional scanned-PDF OCR with page-level provenance;
- source/page provenance;
- engineering Markdown report;
- JSON/Markdown CLI output;
- automated test configuration.

Not yet implemented:

- OCR for scanned documents;
- robust table extraction;
- broader industrial unit normalization;
- broad industrial unit normalization;
- Excel report generation;
- PDF report generation;
- web UI;
- persistent database;
- multi-user authentication;
- production deployment.

## 12. Acceptance criteria for the portfolio v1

The portfolio v1 is considered functionally complete when a reviewer can:

1. inspect the repository;
2. install the project dependencies;
3. run the supplied RFQ example;
4. see deterministic technical compliance results;
5. inspect supporting evidence/status fields;
6. generate the Markdown engineering report;
7. understand the boundary between LLM extraction and deterministic engineering logic;
8. reproduce the documented workflow from the README;
9. run the project's automated validation suite when the repository environment permits it.

CI/test execution status must be verified separately from static repository configuration.

## 13. Portfolio positioning

This project demonstrates the application of AI and software engineering to a concrete industrial/EPC workflow.

Relevant engineering concepts include:

- RFQ and vendor quotation review;
- technical-commercial evaluation;
- industrial automation;
- EPC delivery;
- document traceability;
- FAT/SAT-oriented documentation;
- engineering change/review workflows;
- human-in-the-loop decision support.

Relevant software/AI capabilities include:

- Python;
- structured data modelling;
- LLM integration;
- grounded extraction;
- document intelligence;
- deterministic rule engines;
- evidence traceability;
- CLI/API-oriented design;
- testing and CI/CD.

The project should be presented as an engineering decision-support prototype, not as a production procurement or autonomous engineering system.

## 14. Future product roadmap

Potential future releases may add:

### Document intelligence
- OCR;
- table extraction;
- better section/row-level evidence locations;
- batch document processing.

### Engineering intelligence
- configurable engineering rules;
- ranges and tolerances;
- relational operators;
- broader unit normalization;
- IEC/IEEE requirement libraries.

### Reporting
- Excel output;
- PDF output;
- evidence visualization;
- review/approval workflow.

### Application layer
- web UI;
- drag-and-drop document upload;
- REST API;
- database-backed project history;
- authentication and role-based access;
- cloud deployment.

These are roadmap items, not claims about current functionality.

## 15. Product principle

**AI reads and structures. Deterministic logic compares. Evidence explains. Engineers decide.**
