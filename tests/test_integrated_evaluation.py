from freellmpool.integrated_evaluation import build_integrated_evaluation


def _technical(score: float = 100.0, **extra: int | float) -> dict[str, object]:
    return {
        "vendor": "A",
        "technical_score": score,
        "evidence_coverage_pct": 100.0,
        "conflict_count": 0,
        "major_deviation_count": 0,
        "missing_evidence_count": 0,
        **extra,
    }


def _commercial(vendor: str, price: float, lead: float, warranty: float, flags: list[str] | None = None) -> dict[str, object]:
    return {
        "vendor": vendor,
        "price": price,
        "currency": "USD",
        "lead_time_weeks": lead,
        "warranty_months": warranty,
        "payment_terms": "30% advance",
        "flags": flags or [],
    }


def test_integrated_score_uses_explicit_seventy_thirty_formula() -> None:
    result = build_integrated_evaluation(
        [_technical(80.0)],
        [_commercial("A", 100.0, 10.0, 12.0)],
    )
    assert result["status"] == "READY_FOR_HUMAN_SELECTION"
    profile = result["vendor_profiles"][0]
    assert profile["technical_score"] == 80.0
    assert profile["commercial_score"] == 100.0
    assert profile["integrated_score"] == 86.0


def test_technical_gate_blocks_integrated_selection() -> None:
    result = build_integrated_evaluation(
        [_technical(90.0, major_deviation_count=1)],
        [_commercial("A", 100.0, 10.0, 12.0)],
    )
    assert result["status"] == "TECHNICAL_REVIEW_REQUIRED"
    assert result["vendor_profiles"][0]["technical_gate"] == "BLOCKED"
    assert result["vendor_profiles"][0]["disposition"] == "TECHNICAL_REVIEW_REQUIRED"


def test_commercial_flags_require_review() -> None:
    result = build_integrated_evaluation(
        [_technical()],
        [_commercial("A", 100.0, 10.0, 12.0, ["EVIDENCE_REVIEW"])],
    )
    assert result["status"] == "COMMERCIAL_REVIEW_REQUIRED"
    assert result["vendor_profiles"][0]["commercial_gate"] == "REVIEW"


def test_mixed_currencies_are_not_scored_as_comparable() -> None:
    rows = [
        _commercial("A", 100.0, 10.0, 12.0),
        {**_commercial("B", 90.0, 9.0, 24.0), "currency": "EUR"},
    ]
    result = build_integrated_evaluation(
        [_technical(), {**_technical(), "vendor": "B"}],
        rows,
    )
    assert result["status"] == "COMMERCIAL_COMPARABILITY_REVIEW_REQUIRED"
    assert all(item["commercial_gate"] == "REVIEW" for item in result["vendor_profiles"])


def test_missing_commercial_data_fails_closed() -> None:
    result = build_integrated_evaluation(
        [_technical()],
        [],
    )
    profile = result["vendor_profiles"][0]
    assert result["status"] == "COMMERCIAL_REVIEW_REQUIRED"
    assert profile["disposition"] == "COMMERCIAL_REVIEW_REQUIRED"
    assert "COMMERCIAL_DATA_MISSING" in profile["commercial_flags"]


def test_integrated_output_is_deterministic_and_does_not_select_supplier() -> None:
    technical = [_technical(90.0), {**_technical(95.0), "vendor": "B"}]
    commercial = [_commercial("A", 100.0, 10.0, 12.0), _commercial("B", 110.0, 8.0, 24.0)]
    first = build_integrated_evaluation(technical, commercial)
    second = build_integrated_evaluation(technical, commercial)
    assert first == second
    assert "supplier is selected automatically" in first["decision_note"]


def test_custom_weighting_changes_integrated_score() -> None:
    technical = [_technical(80.0)]
    commercial = [_commercial("A", 100.0, 10.0, 12.0)]
    result = build_integrated_evaluation(
        technical,
        commercial,
        technical_weight=40.0,
        commercial_weight=60.0,
    )
    assert result["vendor_profiles"][0]["integrated_score"] == 92.0
    assert result["formula"]["weights"] == {"technical": 40.0, "commercial": 60.0}


def test_invalid_weights_are_rejected() -> None:
    try:
        build_integrated_evaluation(
            [_technical()],
            [_commercial("A", 100.0, 10.0, 12.0)],
            technical_weight=60.0,
            commercial_weight=30.0,
        )
    except ValueError as exc:
        assert "total 100%" in str(exc)
    else:
        raise AssertionError("invalid weighting was accepted")
