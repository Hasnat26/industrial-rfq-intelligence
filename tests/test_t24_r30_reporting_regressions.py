from __future__ import annotations

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
    requirements, vendor_data, commercial_data = load_rfq_input(fixture)
    return build_report(requirements, vendor_data, commercial_data)


def test_original_fixture_missing_and_conflicting_claims_are_actionable() -> None:
    report = _original_fixture_report()
    summary = report["summary"]
    actions = report["review_actions"]
    action_keys = {(row["vendor"], row["parameter"], row["status"]) for row in actions}

    assert summary["claims_requiring_review"] == 2
    assert summary["unverified_fields"] == 2
    assert ("Vendor B", "VFD overload rating", "UNVERIFIED") in action_keys
    assert ("Vendor C", "Efficiency class", "UNVERIFIED") in action_keys

    missing = next(row for row in actions if row["vendor"] == "Vendor B" and row["parameter"] == "VFD overload rating")
    conflict = next(row for row in actions if row["vendor"] == "Vendor C" and row["parameter"] == "Efficiency class")
    assert missing["requirement"]
    assert missing["source"] == ""  # no source exists for an absent claim
    assert conflict["requirement"]
    assert conflict["claim_status"] == "CONTRADICTED"
    assert conflict["source"] == "Vendor C quotation"
    assert "2" in conflict["page"]


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
