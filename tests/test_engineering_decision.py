from freellmpool.engineering_decision import build_engineering_decision_summary


def test_conflict_takes_priority_over_other_review_flags() -> None:
    result = build_engineering_decision_summary(
        [
            {
                "vendor": "A",
                "technical_score": 50.0,
                "evidence_coverage_pct": 50.0,
                "compliant_count": 1,
                "deviation_count": 0,
                "major_deviation_count": 0,
                "minor_deviation_count": 0,
                "conflict_count": 1,
                "missing_evidence_count": 1,
            }
        ]
    )
    assert result["status"] == "ENGINEERING_REVIEW_REQUIRED"
    profile = result["vendor_profiles"][0]
    assert profile["disposition"] == "CRITICAL_CONFLICT_REVIEW"
    assert "conflicting requirement" in profile["rationale"][0]


def test_major_deviation_precedes_missing_evidence() -> None:
    result = build_engineering_decision_summary(
        [
            {
                "vendor": "B",
                "technical_score": 62.5,
                "evidence_coverage_pct": 75.0,
                "compliant_count": 1,
                "deviation_count": 1,
                "major_deviation_count": 1,
                "minor_deviation_count": 0,
                "conflict_count": 0,
                "missing_evidence_count": 1,
            }
        ]
    )
    assert result["vendor_profiles"][0]["disposition"] == "MAJOR_DEVIATION_REVIEW"


def test_complete_vendor_is_ready_for_commercial_review() -> None:
    result = build_engineering_decision_summary(
        [
            {
                "vendor": "C",
                "technical_score": 100.0,
                "evidence_coverage_pct": 100.0,
                "compliant_count": 4,
                "deviation_count": 0,
                "major_deviation_count": 0,
                "minor_deviation_count": 0,
                "conflict_count": 0,
                "missing_evidence_count": 0,
            }
        ]
    )
    assert result["status"] == "TECHNICAL_PROFILES_READY_FOR_COMMERCIAL_REVIEW"
    assert result["vendor_profiles"][0]["disposition"] == "TECHNICALLY_COMPLIANT_PROFILE"


def test_summary_is_deterministic_and_does_not_select_supplier() -> None:
    vendors = [
        {
            "vendor": "B",
            "technical_score": 90.0,
            "evidence_coverage_pct": 100.0,
            "compliant_count": 2,
            "deviation_count": 0,
            "major_deviation_count": 0,
            "minor_deviation_count": 0,
            "conflict_count": 0,
            "missing_evidence_count": 0,
        },
        {
            "vendor": "A",
            "technical_score": 100.0,
            "evidence_coverage_pct": 100.0,
            "compliant_count": 2,
            "deviation_count": 0,
            "major_deviation_count": 0,
            "minor_deviation_count": 0,
            "conflict_count": 0,
            "missing_evidence_count": 0,
        },
    ]
    first = build_engineering_decision_summary(vendors)
    second = build_engineering_decision_summary(vendors)
    assert first == second
    assert "selected" not in " ".join(first["decision_basis"]).lower()
