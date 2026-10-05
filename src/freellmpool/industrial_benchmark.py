"""Benchmark utilities for Industrial RFQ extraction and deterministic comparison."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .industrial import (
    CommercialValue,
    EvidenceProvenance,
    Requirement,
    VendorValue,
    build_matrix,
)


def _require_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark requires a non-empty 'cases' array")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be an object")
        if not isinstance(case.get("id"), str) or not case["id"].strip():
            raise ValueError(f"cases[{index}].id must be a non-empty string")
        if not isinstance(case.get("requirements"), list) or not case["requirements"]:
            raise ValueError(f"cases[{index}].requirements must be a non-empty array")
        if not isinstance(case.get("vendor_data"), list) or not case["vendor_data"]:
            raise ValueError(f"cases[{index}].vendor_data must be a non-empty array")
        if not isinstance(case.get("expected_statuses"), list):
            raise ValueError(f"cases[{index}].expected_statuses must be an array")
    return cases


def load_benchmark(path: str | Path) -> list[dict[str, Any]]:
    """Load the versioned benchmark manifest without executing an LLM."""
    benchmark_path = Path(path)
    try:
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read benchmark '{benchmark_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid benchmark JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("benchmark must be a JSON object")
    version = payload.get("benchmark_version")
    if version != "1.0":
        raise ValueError(f"unsupported benchmark_version: {version!r}")
    return _require_cases(payload)


def _case_inputs(case: dict[str, Any]) -> tuple[list[Requirement], list[VendorValue], list[CommercialValue]]:
    requirements = [
        Requirement(item["tag"], item["parameter"], item["required"])
        for item in case["requirements"]
    ]
    vendor_data = [
        VendorValue(
            item["vendor"],
            item["parameter"],
            item["value"],
            item.get("evidence", ""),
            item.get("claim_status", "UNVERIFIED"),
            (
                EvidenceProvenance(
                    source=str(item["provenance"].get("source", "")),
                    page=item["provenance"].get("page"),
                    section=item["provenance"].get("section"),
                    table=item["provenance"].get("table"),
                    cell=item["provenance"].get("cell"),
                )
                if isinstance(item.get("provenance"), dict)
                else None
            ),
        )
        for item in case["vendor_data"]
    ]
    return requirements, vendor_data, []


def evaluate_deterministic_case(case: dict[str, Any]) -> dict[str, Any]:
    """Score deterministic compliance against the gold structured case."""
    requirements, vendor_data, _ = _case_inputs(case)
    matrix = build_matrix(requirements, vendor_data)
    expected_statuses = list(case["expected_statuses"])
    actual_statuses = [row["status"] for row in matrix]
    status_matches = sum(
        actual == expected
        for actual, expected in zip(actual_statuses, expected_statuses, strict=False)
    )
    claim_status_matches = None
    expected_claim_statuses = case.get("expected_claim_statuses")
    if expected_claim_statuses is not None:
        actual_claims = [row["claim_status"] for row in matrix]
        claim_status_matches = sum(
            actual == expected
            for actual, expected in zip(actual_claims, expected_claim_statuses, strict=False)
        )
    expected_count = len(expected_statuses)
    return {
        "case_id": case["id"],
        "status_accuracy": status_matches / expected_count if expected_count else 1.0,
        "expected_statuses": expected_statuses,
        "actual_statuses": actual_statuses,
        "claim_status_accuracy": (
            claim_status_matches / len(expected_claim_statuses)
            if claim_status_matches is not None and expected_claim_statuses
            else None
        ),
        "matrix_rows": len(matrix),
    }


def evaluate_benchmark(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate deterministic benchmark metrics without ranking vendors."""
    results = [evaluate_deterministic_case(case) for case in cases]
    total_expected = sum(len(item["expected_statuses"]) for item in results)
    matched = sum(
        round(item["status_accuracy"] * len(item["expected_statuses"]))
        for item in results
    )
    claim_items = [
        item for item in results if item["claim_status_accuracy"] is not None
    ]
    return {
        "cases": len(results),
        "status_accuracy": matched / total_expected if total_expected else 1.0,
        "claim_status_accuracy": (
            sum(
                item["claim_status_accuracy"] * 1
                for item in claim_items
                if item["claim_status_accuracy"] is not None
            ) / len(claim_items)
            if claim_items
            else None
        ),
        "case_results": results,
    }


def evaluate_extraction(
    expected_requirements: Sequence[Requirement],
    expected_vendor_data: Sequence[VendorValue],
    actual_requirements: Sequence[Requirement],
    actual_vendor_data: Sequence[VendorValue],
) -> dict[str, float]:
    """Score LLM extraction separately from deterministic compliance."""
    expected_req = {
        (item.tag, item.parameter, item.required)
        for item in expected_requirements
    }
    actual_req = {
        (item.tag, item.parameter, item.required)
        for item in actual_requirements
    }
    expected_vendor = {
        (item.vendor, item.parameter, item.value)
        for item in expected_vendor_data
    }
    actual_vendor = {
        (item.vendor, item.parameter, item.value)
        for item in actual_vendor_data
    }
    actual_evidence = sum(bool(item.evidence) for item in actual_vendor_data)
    expected_provenance = sum(item.provenance is not None for item in expected_vendor_data)
    actual_provenance = sum(item.provenance is not None for item in actual_vendor_data)

    return {
        "requirement_precision": len(actual_req & expected_req) / len(actual_req) if actual_req else 1.0,
        "requirement_recall": len(actual_req & expected_req) / len(expected_req) if expected_req else 1.0,
        "vendor_field_precision": len(actual_vendor & expected_vendor) / len(actual_vendor) if actual_vendor else 1.0,
        "vendor_field_recall": len(actual_vendor & expected_vendor) / len(expected_vendor) if expected_vendor else 1.0,
        "evidence_coverage": actual_evidence / len(expected_vendor_data) if expected_vendor_data else 1.0,
        "provenance_coverage": actual_provenance / expected_provenance if expected_provenance else 1.0,
    }


__all__ = [
    "load_benchmark",
    "evaluate_deterministic_case",
    "evaluate_benchmark",
    "evaluate_extraction",
]
