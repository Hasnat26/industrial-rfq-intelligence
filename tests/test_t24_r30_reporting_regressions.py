from __future__ import annotations

import hashlib
from pathlib import Path

from freellmpool.industrial import build_report, load_rfq_input
from freellmpool.industrial_report import render_engineering_report


def _unescaped_pipe_cells(line: str) -> int:
    """Count Markdown table cells while ignoring escaped literal pipes."""
    cells = 0
    escaped = False
    for char in line:
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == "|" and not escaped:
            cells += 1
        escaped = False
    return max(0, cells - 1)  # outer table delimiters are not cells


def _original_fixture_report():
    fixture = Path(__file__).parent / "fixtures" / "t24_r30_original_rfq.json"
    expected_sha256 = "4391ace61123e12f766ac8633d1860026e7a173cd9c5de47a38b7ea352a9930e"
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == expected_sha256
    requirements, vendor_data, commercial_data = load_rfq_input(fixture)
    return build_report(requirements, vendor_data, commercial_data)


def test_original_fixture_missing_and_conflicting_claims_are_actionable() -> None:
    report = _original_fixture_report()
    summary = report["summary"]
    actions = report["review_actions"]
    action_keys = {(row["vendor"], row["parameter"], row["status"]) for row in actions}

    # Two verified deviations and two unverified/contradictory obligations are
    # surfaced for engineering review; the summary must count all four uniquely.
    assert summary["claims_requiring_review"] == 4
    assert summary["unverified_fields"] == 2
    assert action_keys == {
        ("Vendor B", "Efficiency class", "DEVIATION"),
        ("Vendor B", "VFD overload rating", "UNVERIFIED"),
        ("Vendor C", "Efficiency class", "UNVERIFIED"),
        ("Vendor C", "VFD overload rating", "DEVIATION"),
    }

    b_efficiency = next(row for row in actions if row["vendor"] == "Vendor B" and row["parameter"] == "Efficiency class")
    assert b_efficiency["claim_status"] == "VERIFIED"
    assert b_efficiency["source"] == "Vendor B quotation"
    assert b_efficiency["page"] == "2"
    assert b_efficiency["section"] == "Technical Datasheet"

    c_vfd = next(row for row in actions if row["vendor"] == "Vendor C" and row["parameter"] == "VFD overload rating")
    assert c_vfd["claim_status"] == "VERIFIED"
    assert c_vfd["source"] == "Vendor C quotation"
    assert c_vfd["page"] == "2"

    missing = next(row for row in actions if row["vendor"] == "Vendor B" and row["parameter"] == "VFD overload rating")
    conflict = next(row for row in actions if row["vendor"] == "Vendor C" and row["parameter"] == "Efficiency class")
    assert missing["requirement"]
    assert missing["source"] == ""  # no source exists for an absent claim
    assert conflict["requirement"]
    assert conflict["claim_status"] == "CONTRADICTED"
    assert conflict["source"] == "Vendor C quotation"
    assert conflict["page"] == "2"


def test_markdown_tables_have_consistent_cells_for_original_fixture() -> None:
    rendered = render_engineering_report(_original_fixture_report())
    lines = rendered.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|") or index + 1 >= len(lines):
            continue
        following = lines[index + 1]
        if not following.startswith("|-") and not following.startswith("| -"):
            continue
        expected = _unescaped_pipe_cells(line)
        assert _unescaped_pipe_cells(following) == expected
        row_index = index + 2
        while row_index < len(lines) and lines[row_index].startswith("|"):
            assert _unescaped_pipe_cells(lines[row_index]) == expected
            row_index += 1

    conflict_row = next(line for line in lines if line.startswith("| R-03 | Vendor C |") and "CONFLICTING" in line)
    assert r"\|" in conflict_row
    assert "Vendor C quotation" in conflict_row


def test_markdown_cell_escapes_literal_pipes_and_newlines() -> None:
    from freellmpool.industrial import Requirement, VendorValue, build_report

    report = build_report(
        [Requirement("R-01", "Efficiency class", "IE3")],
        [VendorValue("Vendor X", "Efficiency class", "IE3", "quote p.2 | table A\ncontinued evidence", "VERIFIED")],
    )
    rendered = render_engineering_report(report)
    assert r"quote p.2 \| table A<br>continued evidence" in rendered
    row = next(line for line in rendered.splitlines() if line.startswith("| R-01 | Vendor X |"))
    assert _unescaped_pipe_cells(row) == 7


def test_sample_verified_deviation_counts_as_one_review_obligation() -> None:
    """A supported quotation claim can still require review when it deviates."""
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples" / "industrial_rfq" / "sample_input.json"
    requirements, vendor_data, commercial_data = load_rfq_input(fixture)
    report = build_report(requirements, vendor_data, commercial_data)

    deviation = next(
        row for row in report["matrix"]
        if row["vendor"] == "Vendor B" and row["parameter"] == "Efficiency class"
    )
    evidence = next(
        row for row in report["evidence_register"]
        if row["source_type"] == "technical_quotation"
        and row["vendor"] == "Vendor B"
        and row["field"] == "Efficiency class"
    )
    action = next(
        row for row in report["review_actions"]
        if row["vendor"] == "Vendor B" and row["parameter"] == "Efficiency class"
    )

    assert deviation["status"] == "DEVIATION"
    assert deviation["claim_status"] == "VERIFIED"
    assert evidence["claim_status"] == "VERIFIED"
    assert evidence["review_required"] == "NO"
    assert action["status"] == "DEVIATION"
    assert action["claim_status"] == "VERIFIED"
    assert action["source"] == "Vendor quotation"
    assert action["page"] == "2"
    assert report["summary"]["claims_requiring_review"] == 1
    assert len(report["review_actions"]) == 1


def test_technical_matrix_and_evidence_review_are_deduplicated_and_commercial_review_is_counted() -> None:
    from freellmpool.industrial import CommercialValue, Requirement, VendorValue

    report = build_report(
        [Requirement("R-01", "Efficiency class", "IE3")],
        [VendorValue("Vendor X", "Efficiency class", "IE2", "Vendor X quotation p.2", "UNVERIFIED")],
        [
            CommercialValue(
                "Vendor X", "9000", "USD", "14 weeks", "6 months",
                "100% advance", "Vendor X commercial quotation p.3", "UNVERIFIED"
            )
        ],
    )

    technical_entry = next(
        row for row in report["evidence_register"]
        if row["source_type"] == "technical_quotation"
    )
    commercial_entry = next(
        row for row in report["evidence_register"]
        if row["source_type"] == "commercial_quotation"
    )
    assert technical_entry["review_required"] == "YES"
    assert commercial_entry["review_required"] == "YES"
    # The technical matrix and its evidence-register entry represent one claim;
    # the separate commercial review obligation remains independently counted.
    assert report["summary"]["claims_requiring_review"] == 2
