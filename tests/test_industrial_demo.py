from pathlib import Path

from freellmpool.industrial import (
    Requirement,
    VendorValue,
    build_matrix,
    build_report,
)


def test_build_matrix_detects_vendor_deviation() -> None:
    matrix = build_matrix()
    deviations = [row for row in matrix if row["status"] == "DEVIATION"]

    assert len(matrix) == 8
    assert len(deviations) == 1
    assert deviations[0]["vendor"] == "Vendor B"
    assert deviations[0]["parameter"] == "Efficiency class"
    assert deviations[0]["offered"] == "IE2"
    assert deviations[0]["required"] == "IE3"
    assert deviations[0]["evidence"] == "Quotation p.2"


def test_missing_fields_are_unverified() -> None:
    requirements = [Requirement("R-01", "Rated voltage", "415 V")]
    vendor_data = [
        VendorValue("Vendor A", "Motor power", "75 kW", "Quotation p.1"),
    ]

    matrix = build_matrix(requirements, vendor_data)
    assert matrix[0]["status"] == "UNVERIFIED"
    assert matrix[0]["claim_status"] == "UNVERIFIED"
    assert matrix[0]["evidence"] == "No matching quotation field"


def test_report_contains_review_actions_and_summary() -> None:
    report = build_report()
    assert report["workflow"] == "rfq-compliance-review"
    assert report["product"] == "industrial-rfq-intelligence"
    summary = report["summary"]
    assert summary["requirements_checked"] == 4
    assert summary["vendors_checked"] == 2
    assert summary["deviations"] == 1
    assert len(report["review_actions"]) == 1


def test_load_rfq_input_from_json(tmp_path) -> None:
    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "rfq.json"
    path.write_text(
        """{
          "requirements": [
            {"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}
          ],
          "vendor_data": [
            {"vendor": "Vendor X", "parameter": "Rated voltage",
             "value": "400 V", "evidence": "Quotation p.3",
             "claim_status": "VERIFIED"}
          ]
        }""",
        encoding="utf-8",
    )

    requirements, vendor_data, commercial = load_rfq_input(path)
    assert requirements[0].parameter == "Rated voltage"
    assert vendor_data[0].vendor == "Vendor X"
    assert vendor_data[0].claim_status == "VERIFIED"


def test_load_rfq_input_rejects_missing_required_field(tmp_path) -> None:
    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "invalid.json"
    path.write_text(
        '{"requirements": [{"tag": "R-01"}], "vendor_data": [{"vendor": "Vendor X"}]}',
        encoding="utf-8",
    )

    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "missing field: parameter" in str(exc)
    else:
        raise AssertionError("invalid RFQ input was accepted")


def test_llm_extraction_reuses_strict_validation() -> None:
    from freellmpool.industrial import extract_rfq_with_llm

    class FakeReply:
        text = '{"requirements":[{"tag":"R-01","parameter":"Rated voltage","required":"415 V"}],"vendor_data":[{"vendor":"Vendor X","parameter":"Rated voltage","value":"400 V","evidence":"Vendor X quotation p.1","claim_status":"VERIFIED"}]}'

    class FakePool:
        def ask(self, *args, **kwargs):
            return FakeReply()

    requirements, vendor_data, commercial = extract_rfq_with_llm(
        FakePool(),
        "Supply 415 V motor.",
        [{"vendor": "Vendor X", "text": "400 V motor.", "evidence_prefix": "Vendor X quotation"}],
    )
    assert requirements[0].required == "415 V"
    assert vendor_data[0].value == "400 V"
    assert vendor_data[0].evidence == "Vendor X quotation p.1"
    assert commercial == []


def test_conflicting_vendor_claims_are_unverified() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [
            VendorValue("Vendor X", "Rated voltage", "415 V", "quote p.1", "VERIFIED"),
            VendorValue("Vendor X", "Nominal voltage", "400 V", "quote p.4", "VERIFIED"),
        ],
    )
    assert matrix[0]["status"] == "UNVERIFIED"
    assert matrix[0]["claim_status"] == "CONTRADICTED"
    assert matrix[0]["offered"] == "CONFLICTING"
    assert "quote p.1: 415 V" in matrix[0]["evidence"]
    assert "quote p.4: 400 V" in matrix[0]["evidence"]


def test_missing_evidence_forces_unverified(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "rfq.json"
    path.write_text(
        json.dumps({
            "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
            "vendor_data": [{
                "vendor": "Vendor X",
                "parameter": "Rated voltage",
                "value": "415 V",
                "claim_status": "VERIFIED",
            }],
            "commercial_data": [{
                "vendor": "Vendor X",
                "price": "10000",
                "currency": "USD",
                "lead_time": "8 weeks",
                "warranty": "12 months",
                "payment_terms": "30% advance",
                "claim_status": "VERIFIED",
            }],
        }),
        encoding="utf-8",
    )
    _, vendor_data, commercial = load_rfq_input(path)
    assert vendor_data[0].evidence == ""
    assert vendor_data[0].claim_status == "UNVERIFIED"
    assert commercial[0].evidence == ""
    assert commercial[0].claim_status == "UNVERIFIED"


def test_claim_status_defaults_to_unverified(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "rfq.json"
    path.write_text(
        json.dumps({
            "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
            "vendor_data": [{
                "vendor": "Vendor X",
                "parameter": "Rated voltage",
                "value": "415 V",
                "evidence": "quote p.1",
            }],
        }),
        encoding="utf-8",
    )
    _, vendor_data, commercial = load_rfq_input(path)
    assert vendor_data[0].claim_status == "UNVERIFIED"
    assert commercial == []


def test_load_rfq_input_includes_commercial_data(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    payload = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor A", "parameter": "Rated voltage", "value": "415 V", "evidence": "p.1"}],
        "commercial_data": [{
            "vendor": "Vendor A", "price": "10000", "currency": "USD",
            "lead_time": "8 weeks", "warranty": "24 months",
            "payment_terms": "30% advance", "evidence": "p.3"
        }],
    }
    path = tmp_path / "rfq.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    requirements, vendor_data, commercial = load_rfq_input(path)
    assert requirements[0].required == "415 V"
    assert vendor_data[0].value == "415 V"
    assert commercial[0].price == "10000"
    assert commercial[0].warranty == "24 months"


def test_parameter_alias_and_unit_normalization() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    requirements = [
        Requirement("R-01", "Rated voltage", "0.415 kV"),
        Requirement("R-02", "Motor power", "75 kW"),
    ]
    vendor_data = [
        VendorValue("Vendor X", "Nominal voltage", "415 V", "quotation p.1"),
        VendorValue("Vendor X", "Rated power", "75000 W", "quotation p.1"),
    ]
    matrix = build_matrix(requirements, vendor_data)
    assert [row["status"] for row in matrix] == ["COMPLIANT", "COMPLIANT"]
    assert matrix[0]["offered_parameter"] == "Nominal voltage"


def test_broader_engineering_unit_normalization() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        ("Current", "1 kA", "1000 A"),
        ("Frequency", "50 Hz", "0.05 kHz"),
        ("Speed", "1500 rpm", "1500 rpm"),
        ("Torque", "1 kNm", "1000 Nm"),
        ("Temperature", "40 °C", "40 C"),
        ("Pressure", "1 MPa", "10 bar"),
        ("Length", "1 m", "1000 mm"),
        ("Mass", "1 t", "1000 kg"),
    ]

    for parameter, required, offered in cases:
        matrix = build_matrix(
            [Requirement("R-01", parameter, required)],
            [VendorValue("Vendor X", parameter, offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == "COMPLIANT"


def test_broader_engineering_unit_mismatch_is_deviation() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Pressure", "1 MPa")],
        [VendorValue("Vendor X", "Pressure", "9 bar", "quote p.1", "VERIFIED")],
    )
    assert matrix[0]["status"] == "DEVIATION"


def test_engineering_operators_ranges_and_tolerance() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        (Requirement("R-01", "Motor power", ">= 75 kW"), "75 kW"),
        (Requirement("R-02", "Rated voltage", "<= 415 V"), "415 V"),
        (Requirement("R-03", "Rated voltage", "> 400 V"), "415 V"),
        (Requirement("R-04", "Motor power", "70 to 80 kW"), "75 kW"),
        (Requirement("R-05", "Rated voltage", "400-450 V"), "450 V"),
        (Requirement("R-06", "Rated voltage", "415 V ±5%"), "415 V"),
        (Requirement("R-07", "Rated voltage", "415 V +/-5%"), "435 V"),
    ]

    for requirement, offered in cases:
        matrix = build_matrix(
            [requirement],
            [VendorValue("Vendor X", requirement.parameter, offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == "COMPLIANT"


def test_engineering_operator_deviation_is_detected() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Motor power", ">= 75 kW")],
        [VendorValue("Vendor X", "Motor power", "72 kW", "quote p.1", "VERIFIED")],
    )
    assert matrix[0]["status"] == "DEVIATION"


def test_unit_mismatch_remains_deviation() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [VendorValue("Vendor X", "Voltage", "400 V", "quotation p.1")],
    )
    assert matrix[0]["status"] == "DEVIATION"


def test_report_contains_evidence_register_and_review_flags() -> None:
    from freellmpool.industrial import CommercialValue, VendorValue, build_report
    report = build_report(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [VendorValue("Vendor X", "Voltage", "415 V", "quote p.1", "PARTIALLY VERIFIED")],
        [CommercialValue("Vendor X", "10000", "USD", "8 weeks", "12 months", "30% advance", "quote p.3", "VERIFIED")],
    )
    assert report["summary"]["evidence_records"] == 2
    assert report["summary"]["claims_requiring_review"] == 1
    assert report["evidence_register"][0]["review_required"] == "YES"
    assert report["evidence_register"][1]["review_required"] == "NO"


def test_document_ingestion_preserves_source_and_page(tmp_path) -> None:
    from freellmpool.industrial import document_text, extract_document_pages

    path = tmp_path / "vendor_quote.txt"
    path.write_text("Rated voltage: 415 V\nMotor power: 75 kW", encoding="utf-8")
    pages = extract_document_pages(path)
    assert pages[0].source.endswith("vendor_quote.txt")
    assert pages[0].page == 1
    assert "Rated voltage: 415 V" in document_text(pages)


def test_document_ingestion_rejects_unsupported_type(tmp_path) -> None:
    from freellmpool.industrial import extract_document_pages

    path = tmp_path / "quote.docx"
    path.write_bytes(b"not supported")
    try:
        extract_document_pages(path)
    except ValueError as exc:
        assert "unsupported document type" in str(exc)
    else:
        raise AssertionError("unsupported document type was accepted")


def test_document_rfq_extraction_passes_provenance_to_llm() -> None:
    from freellmpool.industrial import extract_rfq_documents_with_llm

    class FakeReply:
        text = '{"requirements":[{"tag":"R-01","parameter":"Rated voltage","required":"415 V"}],"vendor_data":[{"vendor":"Vendor X","parameter":"Rated voltage","value":"415 V","evidence":"vendor_quote.txt | PAGE: 1","claim_status":"VERIFIED"}],"commercial_data":[]}'

    class FakePool:
        def __init__(self):
            self.prompt = None

        def ask(self, prompt, **kwargs):
            self.prompt = prompt
            return FakeReply()

    rfq = __import__("pathlib").Path("tests") / "_rfq_m7_temp.txt"
    quote = __import__("pathlib").Path("tests") / "_quote_m7_temp.txt"
    try:
        rfq.write_text("Required rated voltage: 415 V", encoding="utf-8")
        quote.write_text("Rated voltage: 415 V", encoding="utf-8")
        pool = FakePool()
        requirements, vendor_data, commercial = extract_rfq_documents_with_llm(
            pool,
            rfq,
            [{"vendor": "Vendor X", "path": quote}],
            use_markdown=False,
        )
        assert "[SOURCE:" in pool.prompt
        assert "PAGE: 1" in pool.prompt
        assert requirements[0].required == "415 V"
        assert vendor_data[0].evidence == "vendor_quote.txt | PAGE: 1"
        assert commercial == []
    finally:
        rfq.unlink(missing_ok=True)
        quote.unlink(missing_ok=True)
def test_sample_rfq_is_reproducible_and_report_matches_fixture() -> None:
    from freellmpool.industrial import build_report, load_rfq_input
    from freellmpool.industrial_report import render_engineering_report

    root = Path(__file__).resolve().parents[1]
    input_path = root / "examples" / "industrial_rfq" / "sample_input.json"
    report_path = root / "examples" / "industrial_rfq" / "sample_report.md"

    requirements, vendor_data, commercial = load_rfq_input(input_path)
    report = build_report(requirements, vendor_data, commercial)
    rendered = render_engineering_report(report) + "\n"

    assert report["summary"] == {
        "requirements_checked": 4,
        "vendors_checked": 2,
        "matrix_rows": 8,
        "deviations": 1,
        "unverified_fields": 0,
        "commercial_records": 2,
        "evidence_records": 10,
        "claims_requiring_review": 0,
    }
    assert rendered == report_path.read_text(encoding="utf-8")
    assert report["matrix"][6]["status"] == "DEVIATION"
    assert report["matrix"][6]["vendor"] == "Vendor B"
    assert report["matrix"][6]["parameter"] == "Efficiency class"

def test_invalid_claim_status_is_rejected(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "invalid-status.json"
    path.write_text(
        json.dumps({
            "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
            "vendor_data": [{
                "vendor": "Vendor X",
                "parameter": "Rated voltage",
                "value": "415 V",
                "evidence": "quote p.1",
                "claim_status": "GUESS",
            }],
        }),
        encoding="utf-8",
    )
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "invalid claim_status" in str(exc)
    else:
        raise AssertionError("invalid claim_status was accepted")


def test_malformed_json_is_rejected(tmp_path) -> None:
    from freellmpool.industrial import load_rfq_input

    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "invalid RFQ JSON" in str(exc)
    else:
        raise AssertionError("malformed JSON was accepted")


def test_empty_requirements_and_vendor_data_are_rejected(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    cases = [
        {"requirements": [], "vendor_data": [{"vendor": "Vendor X", "parameter": "Voltage", "value": "415 V"}]},
        {"requirements": [{"tag": "R-01", "parameter": "Voltage", "required": "415 V"}], "vendor_data": []},
    ]
    for index, payload in enumerate(cases):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            load_rfq_input(path)
        except ValueError as exc:
            assert "non-empty" in str(exc)
        else:
            raise AssertionError("empty RFQ collection was accepted")


def test_unsupported_numeric_units_do_not_silently_pass() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [VendorValue("Vendor X", "Rated voltage", "415 psi", "quote p.1", "VERIFIED")],
    )
    assert matrix[0]["status"] == "DEVIATION"


def test_unverified_claim_remains_reviewable_even_with_matching_value() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_report

    report = build_report(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [VendorValue("Vendor X", "Rated voltage", "415 V", "quote p.1", "UNVERIFIED")],
    )
    assert report["matrix"][0]["status"] == "COMPLIANT"
    assert report["matrix"][0]["claim_status"] == "UNVERIFIED"
    assert report["summary"]["claims_requiring_review"] == 1


def test_rfq_schema_version_contract(tmp_path) -> None:
    import json

    from freellmpool.industrial import RFQ_SCHEMA_VERSION, load_rfq_input

    base = {
        "schema_version": RFQ_SCHEMA_VERSION,
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V"}],
    }
    path = tmp_path / "versioned.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    requirements, vendor_data, _ = load_rfq_input(path)
    assert requirements[0].tag == "R-01"
    assert vendor_data[0].claim_status == "UNVERIFIED"

    base["schema_version"] = "99.0"
    path.write_text(json.dumps(base), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "unsupported RFQ schema_version" in str(exc)
    else:
        raise AssertionError("unsupported schema version was accepted")


def test_duplicate_requirement_tags_are_rejected(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    payload = {
        "requirements": [
            {"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"},
            {"tag": "R-01", "parameter": "Motor power", "required": "75 kW"},
        ],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V"}],
    }
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "duplicate tag" in str(exc)
    else:
        raise AssertionError("duplicate requirement tag was accepted")


def test_rfq_contract_rejects_non_string_fields(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    payload = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": 415}],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V"}],
    }
    path = tmp_path / "wrong-type.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "fields must be strings" in str(exc)
    else:
        raise AssertionError("non-string requirement field was accepted")


def test_rfq_schema_version_is_supported_and_backward_compatible(tmp_path) -> None:
    import json

    from freellmpool.industrial import RFQ_SCHEMA_VERSION, load_rfq_input

    base = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V", "evidence": "quote p.1"}],
    }
    versioned = tmp_path / "versioned.json"
    versioned.write_text(json.dumps({**base, "schema_version": RFQ_SCHEMA_VERSION}), encoding="utf-8")
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(base), encoding="utf-8")

    assert load_rfq_input(versioned)[0][0].required == "415 V"
    assert load_rfq_input(legacy)[0][0].required == "415 V"


def test_unsupported_rfq_schema_version_fails_closed(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    payload = {
        "schema_version": "99.0",
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V", "evidence": "quote p.1"}],
    }
    path = tmp_path / "future.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "unsupported RFQ schema_version" in str(exc)
    else:
        raise AssertionError("unsupported schema version was accepted")


def test_rfq_schema_rejects_non_string_required_fields_and_duplicate_tags(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    cases = [
        {"requirements": [{"tag": "R-01", "parameter": "Voltage", "required": 415}],
         "vendor_data": [{"vendor": "Vendor X", "parameter": "Voltage", "value": "415 V"}]},
        {"requirements": [
            {"tag": "R-01", "parameter": "Voltage", "required": "415 V"},
            {"tag": "r-01", "parameter": "Power", "required": "75 kW"},
         ], "vendor_data": [{"vendor": "Vendor X", "parameter": "Voltage", "value": "415 V"}]},
    ]
    for index, payload in enumerate(cases):
        path = tmp_path / f"schema-invalid-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            load_rfq_input(path)
        except ValueError as exc:
            assert ("must be a string" in str(exc)) or ("duplicate requirement tag" in str(exc))
        else:
            raise AssertionError("invalid RFQ schema was accepted")


def test_duplicate_vendor_claim_is_rejected_but_conflicting_claims_remain_supported(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    base = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [
            {"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V", "evidence": "quote p.1"},
            {"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V", "evidence": "quote p.1"},
        ],
    }
    path = tmp_path / "duplicate-claim.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "duplicates an existing vendor claim" in str(exc)
    else:
        raise AssertionError("exact duplicate vendor claim was accepted")


def test_duplicate_commercial_vendor_record_is_rejected(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    base = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V"}],
        "commercial_data": [
            {"vendor": "Vendor X", "price": "100", "currency": "USD", "lead_time": "1 week", "warranty": "12 months", "payment_terms": "30%"},
            {"vendor": "vendor x", "price": "200", "currency": "USD", "lead_time": "2 weeks", "warranty": "12 months", "payment_terms": "50%"},
        ],
    }
    path = tmp_path / "duplicate-commercial.json"
    path.write_text(json.dumps(base), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "duplicates commercial data" in str(exc)
    else:
        raise AssertionError("duplicate commercial vendor records were accepted")


def test_provenance_is_normalized_and_preserved(tmp_path) -> None:
    import json

    from freellmpool.industrial import build_report, load_rfq_input

    payload = {
        "schema_version": "1.0",
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{
            "vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V",
            "evidence": "quote p.4", "claim_status": "VERIFIED",
            "provenance": {
                "source": "vendor-quote.pdf", "page": 4,
                "section": "Technical data", "table": "T-02", "cell": "B7",
            },
        }],
    }
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    _, vendor_data, _ = load_rfq_input(path)
    assert vendor_data[0].provenance.source == "vendor-quote.pdf"
    assert vendor_data[0].provenance.page == 4
    assert vendor_data[0].provenance.section == "Technical data"
    assert vendor_data[0].provenance.table == "T-02"
    assert vendor_data[0].provenance.cell == "B7"
    report = build_report(*load_rfq_input(path))
    evidence = report["evidence_register"][0]
    assert evidence["source"] == "vendor-quote.pdf"
    assert evidence["page"] == "4"
    assert evidence["section"] == "Technical data"
    assert evidence["table"] == "T-02"
    assert evidence["cell"] == "B7"


def test_invalid_provenance_page_is_rejected(tmp_path) -> None:
    import json

    from freellmpool.industrial import load_rfq_input

    payload = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{
            "vendor": "Vendor X", "parameter": "Rated voltage", "value": "415 V",
            "evidence": "quote p.0", "claim_status": "VERIFIED",
            "provenance": {"source": "quote.pdf", "page": 0},
        }],
    }
    path = tmp_path / "invalid-provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_rfq_input(path)
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("invalid provenance page was accepted")


def test_parameter_specific_engineering_semantics_reject_incompatible_dimensions() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        ("Rated voltage", "415 V", "415 A"),
        ("Rated current", "100 A", "100 V"),
        ("Motor power", "75 kW", "75 Hz"),
        ("Frequency", "50 Hz", "50 kW"),
        ("Rotational speed", "1500 rpm", "1500 kW"),
        ("Rated torque", "100 Nm", "100 kPa"),
        ("Temperature", "40 °C", "40 bar"),
        ("Pressure", "1 MPa", "1 kW"),
        ("Length", "100 mm", "100 kg"),
        ("Mass", "100 kg", "100 m"),
    ]

    for parameter, required, offered in cases:
        matrix = build_matrix(
            [Requirement("R-01", parameter, required)],
            [VendorValue("Vendor X", parameter, offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == "DEVIATION"


def test_engineering_range_and_tolerance_boundaries_are_inclusive() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        ("Rated voltage", "400-450 V", "400 V"),
        ("Rated voltage", "400-450 V", "450 V"),
        ("Motor power", "75 kW ±5%", "71.25 kW"),
        ("Motor power", "75 kW ±5%", "78.75 kW"),
        ("Pressure", "0.9 to 1.1 MPa", "1.1 MPa"),
    ]

    for parameter, required, offered in cases:
        matrix = build_matrix(
            [Requirement("R-01", parameter, required)],
            [VendorValue("Vendor X", parameter, offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == "COMPLIANT"


def test_engineering_range_and_tolerance_outside_boundaries_are_deviations() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        ("Rated voltage", "400-450 V", "399.9 V"),
        ("Rated voltage", "400-450 V", "450.1 V"),
        ("Motor power", "75 kW ±5%", "71.24 kW"),
        ("Motor power", "75 kW ±5%", "78.76 kW"),
        ("Pressure", "0.9 to 1.1 MPa", "1.101 MPa"),
    ]

    for parameter, required, offered in cases:
        matrix = build_matrix(
            [Requirement("R-01", parameter, required)],
            [VendorValue("Vendor X", parameter, offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == "DEVIATION"


def test_strict_engineering_operators_respect_exclusive_boundaries() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    cases = [
        ("> 400 V", "400 V", "DEVIATION"),
        ("> 400 V", "400.1 V", "COMPLIANT"),
        ("< 500 V", "500 V", "DEVIATION"),
        ("< 500 V", "499.9 V", "COMPLIANT"),
    ]

    for required, offered, expected in cases:
        matrix = build_matrix(
            [Requirement("R-01", "Rated voltage", required)],
            [VendorValue("Vendor X", "Rated voltage", offered, "quote p.1", "VERIFIED")],
        )
        assert matrix[0]["status"] == expected


def test_unsupported_engineering_expression_fails_closed() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_matrix

    matrix = build_matrix(
        [Requirement("R-01", "Rated voltage", "approximately 415 V")],
        [VendorValue("Vendor X", "Rated voltage", "415 V", "quote p.1", "VERIFIED")],
    )
    assert matrix[0]["status"] == "DEVIATION"


def test_commercial_risk_review_normalizes_fields_and_flags_exceptions() -> None:
    from freellmpool.industrial import CommercialValue, build_commercial_risk_review

    rows = build_commercial_risk_review([
        CommercialValue(
            "Vendor A",
            "10,500",
            "usd",
            "14 weeks",
            "6 months",
            "30% advance",
            "quote p.3",
            "VERIFIED",
        ),
        CommercialValue(
            "Vendor B",
            "invalid",
            "USD",
            "TBD",
            "12 months",
            "LC at sight",
            "",
            "UNVERIFIED",
        ),
    ])

    assert rows[0]["price"] == 10500.0
    assert rows[0]["currency"] == "USD"
    assert rows[0]["lead_time_weeks"] == 14.0
    assert rows[0]["warranty_months"] == 6.0
    assert rows[0]["payment_terms"] == "30% advance"
    assert rows[0]["flags"] == ["CURRENCY_NORMALIZATION_REVIEW", "LEAD_TIME_REVIEW", "WARRANTY_REVIEW"]
    assert rows[0]["review_required"] is True

    assert rows[1]["price"] is None
    assert rows[1]["lead_time_weeks"] is None
    assert rows[1]["warranty_months"] == 12.0
    assert rows[1]["flags"] == [
        "EVIDENCE_REVIEW",
        "PRICE_FORMAT_REVIEW",
        "LEAD_TIME_FORMAT_REVIEW",
    ]
    assert rows[1]["review_required"] is True


def test_commercial_risk_review_does_not_rank_or_select_vendors() -> None:
    from freellmpool.industrial import CommercialValue, build_report

    report = build_report(
        [Requirement("R-01", "Rated voltage", "415 V")],
        [VendorValue("Vendor A", "Rated voltage", "415 V", "quote p.1", "VERIFIED")],
        [
            CommercialValue("Vendor A", "10000", "USD", "8 weeks", "24 months", "30% advance", "quote p.3", "VERIFIED"),
            CommercialValue("Vendor B", "9000", "USD", "10 weeks", "18 months", "LC at sight", "quote p.3", "VERIFIED"),
        ],
    )

    risk_review = report["commercial_risk_review"]
    assert len(risk_review) == 2
    assert all("rank" not in row and "winner" not in row for row in risk_review)
    assert [row["vendor"] for row in risk_review] == ["Vendor A", "Vendor B"]


def test_document_intelligence_benchmark_loads_and_scores() -> None:
    from freellmpool.industrial_benchmark import evaluate_benchmark, load_benchmark

    root = Path(__file__).resolve().parents[1]
    cases = load_benchmark(root / "examples" / "industrial_rfq" / "benchmark.json")

    assert len(cases) == 5
    assert {case["source_format"] for case in cases} == {"txt", "pdf", "table", "text"}
    result = evaluate_benchmark(cases)
    assert result["cases"] == 5
    assert result["status_accuracy"] == 1.0
    assert result["claim_status_accuracy"] == 1.0


def test_document_benchmark_separates_extraction_from_compliance() -> None:
    from freellmpool.industrial import Requirement, VendorValue
    from freellmpool.industrial_benchmark import evaluate_extraction, load_benchmark

    root = Path(__file__).resolve().parents[1]
    cases = load_benchmark(root / "examples" / "industrial_rfq" / "benchmark.json")
    case = next(item for item in cases if item["id"] == "TABLE-03")

    expected_requirements = [
        Requirement(item["tag"], item["parameter"], item["required"])
        for item in case["requirements"]
    ]
    expected_vendor_data = [
        VendorValue(
            item["vendor"],
            item["parameter"],
            item["value"],
            item["evidence"],
            item["claim_status"],
        )
        for item in case["vendor_data"]
    ]

    metrics = evaluate_extraction(
        expected_requirements,
        expected_vendor_data,
        expected_requirements,
        expected_vendor_data,
    )
    assert metrics["requirement_precision"] == 1.0
    assert metrics["requirement_recall"] == 1.0
    assert metrics["vendor_field_precision"] == 1.0
    assert metrics["vendor_field_recall"] == 1.0
    assert metrics["evidence_coverage"] == 1.0
    assert metrics["provenance_coverage"] == 1.0


def test_document_benchmark_covers_contradiction_and_ambiguous_cases() -> None:
    from freellmpool.industrial_benchmark import evaluate_deterministic_case, load_benchmark

    root = Path(__file__).resolve().parents[1]
    cases = load_benchmark(root / "examples" / "industrial_rfq" / "benchmark.json")

    contradictory = next(item for item in cases if item["id"] == "CON-05")
    ambiguous = next(item for item in cases if item["id"] == "AMB-04")

    contradiction_result = evaluate_deterministic_case(contradictory)
    ambiguous_result = evaluate_deterministic_case(ambiguous)

    assert contradiction_result["status_accuracy"] == 1.0
    assert contradiction_result["claim_status_accuracy"] == 1.0
    assert ambiguous_result["status_accuracy"] == 1.0


def test_reviewer_workflow_requires_explicit_human_approval() -> None:
    from freellmpool.reviewer_workflow import ReviewSession, ReviewState

    session = ReviewSession("demo").with_input("rfq.json")
    assert session.state is ReviewState.UPLOAD

    extraction = session.transition(ReviewState.EXTRACTION)
    reviewed = extraction.transition(ReviewState.REVIEW, reference="extraction.json")
    assert reviewed.extraction_reference == "extraction.json"
    assert reviewed.human_approved is False

    try:
        reviewed.transition(ReviewState.REPORT, reference="report.md")
    except ValueError as exc:
        assert "explicit human approval" in str(exc)
    else:
        raise AssertionError("report transition bypassed human approval")

    approved = reviewed.approve_review()
    report = approved.transition(ReviewState.REPORT, reference="report.md")
    assert report.state is ReviewState.REPORT
    assert report.report_reference == "report.md"


def test_reviewer_workflow_fails_closed_on_missing_input_and_invalid_transition() -> None:
    from freellmpool.reviewer_workflow import ReviewSession, ReviewState

    session = ReviewSession("demo")
    try:
        session.transition(ReviewState.EXTRACTION)
    except ValueError as exc:
        assert "input_reference" in str(exc)
    else:
        raise AssertionError("extraction started without input")

    try:
        session.transition(ReviewState.REPORT)
    except ValueError as exc:
        assert "invalid reviewer transition" in str(exc)
    else:
        raise AssertionError("invalid workflow transition was accepted")


def test_document_ocr_non_pdf_uses_existing_ingestion(tmp_path) -> None:
    from freellmpool.industrial import extract_document_pages_with_ocr

    path = tmp_path / "quote.txt"
    path.write_text("Rated voltage: 415 V", encoding="utf-8")

    pages = extract_document_pages_with_ocr(path)
    assert len(pages) == 1
    assert pages[0].page == 1
    assert pages[0].text == "Rated voltage: 415 V"


def test_document_ocr_fails_with_actionable_error_when_optional_dependencies_are_missing(
    tmp_path, monkeypatch
) -> None:
    from pypdf import PdfWriter

    from freellmpool.industrial import extract_document_pages_with_ocr

    path = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)

    monkeypatch.setitem(__import__("sys").modules, "fitz", None)
    monkeypatch.setitem(__import__("sys").modules, "pytesseract", None)
    monkeypatch.setitem(__import__("sys").modules, "PIL", None)
    try:
        extract_document_pages_with_ocr(path)
    except ValueError as exc:
        assert "pip install 'industrial-rfq-intelligence[ocr]'" in str(exc)
    else:
        raise AssertionError("OCR unexpectedly ran without optional dependencies")


def test_document_ocr_cli_options_are_exposed() -> None:
    from freellmpool.cli import build_parser

    args = build_parser().parse_args([
        "industrial-document",
        "scanned.pdf",
        "--ocr",
        "--ocr-language",
        "eng",
        "--ocr-min-text-chars",
        "10",
    ])
    assert args.ocr is True
    assert args.ocr_language == "eng"
    assert args.ocr_min_text_chars == 10
