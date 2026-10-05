from __future__ import annotations

from freellmpool.decision_support import build_decision_support
from freellmpool.industrial import Requirement, VendorValue


def _requirements() -> tuple[Requirement, ...]:
    return (
        Requirement("R-01", "Rated voltage", "415 V"),
        Requirement("R-02", "Motor power", "75 kW"),
    )


def test_full_compliance_scores_one_hundred_with_full_evidence() -> None:
    values = (
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
        VendorValue("A", "Motor power", "75 kW", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(_requirements(), values, vendors=["A"])
    vendor = result["vendors"][0]
    assert vendor["technical_score"] == 100.0
    assert vendor["evidence_coverage_pct"] == 100.0
    assert vendor["compliant_count"] == 2
    assert vendor["deviation_count"] == 0
    assert vendor["missing_evidence_count"] == 0


def test_mandatory_deviation_scores_twenty_five_percent() -> None:
    values = (
        VendorValue("A", "Rated voltage", "400 V", "a.pdf p.1", "VERIFIED"),
        VendorValue("A", "Motor power", "75 kW", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(_requirements(), values, vendors=["A"])
    vendor = result["vendors"][0]
    assert vendor["technical_score"] == 62.5
    assert vendor["major_deviation_count"] == 1
    assert vendor["evidence_coverage_pct"] == 100.0


def test_optional_deviation_is_minor_and_less_severe() -> None:
    requirements = (
        Requirement("R-01", "Rated voltage", "415 V"),
        Requirement("R-02", "Motor power", "75 kW"),
    )
    values = (
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
        VendorValue("A", "Motor power", "70 kW", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(
        requirements,
        values,
        vendors=["A"],
        requirement_types={"R-01": "MANDATORY", "R-02": "OPTIONAL"},
    )
    vendor = result["vendors"][0]
    assert vendor["technical_score"] == 75.0
    assert vendor["minor_deviation_count"] == 1
    assert vendor["major_deviation_count"] == 0


def test_missing_evidence_scores_zero_and_is_reported() -> None:
    values = (
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(_requirements(), values, vendors=["A"])
    vendor = result["vendors"][0]
    assert vendor["technical_score"] == 50.0
    assert vendor["missing_evidence_count"] == 1
    assert vendor["evidence_coverage_pct"] == 50.0


def test_conflict_is_critical_and_not_counted_as_missing() -> None:
    values = (
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
        VendorValue("A", "Rated voltage", "400 V", "a.pdf p.2", "VERIFIED"),
        VendorValue("A", "Motor power", "75 kW", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(_requirements(), values, vendors=["A"])
    vendor = result["vendors"][0]
    assert vendor["technical_score"] == 50.0
    assert vendor["conflict_count"] == 1
    assert vendor["missing_evidence_count"] == 0
    conflict = [row for row in result["rows"] if row["requirement"] == "R-01"][0]
    assert conflict["severity"] == "CRITICAL"
    assert conflict["status"] == "UNVERIFIED"


def test_zero_evidence_vendor_remains_visible_and_unverified() -> None:
    values = (
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
    )
    result = build_decision_support(_requirements(), values, vendors=["A", "B"])
    vendors = {item["vendor"]: item for item in result["vendors"]}
    assert set(vendors) == {"A", "B"}
    assert vendors["B"]["technical_score"] == 0.0
    assert vendors["B"]["evidence_coverage_pct"] == 0.0
    assert vendors["B"]["missing_evidence_count"] == 2


def test_output_is_deterministic() -> None:
    values = (
        VendorValue("B", "Rated voltage", "415 V", "b.pdf p.1", "VERIFIED"),
        VendorValue("A", "Rated voltage", "415 V", "a.pdf p.1", "VERIFIED"),
    )
    first = build_decision_support(
        (Requirement("R-01", "Rated voltage", "415 V"),),
        values,
        vendors=["A", "B"],
    )
    second = build_decision_support(
        (Requirement("R-01", "Rated voltage", "415 V"),),
        values,
        vendors=["A", "B"],
    )
    assert first == second
