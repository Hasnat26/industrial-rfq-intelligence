"""Deterministic decision-support calculations for industrial RFQ evaluation.

The module consumes the existing requirement/claim comparison output. It never
selects a vendor and never uses opaque AI scoring: every score component is
derived from explicit requirement outcomes and evidence coverage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from freellmpool.industrial import Requirement, VendorValue, build_matrix

RequirementOutcome = Literal["COMPLIANT", "DEVIATION", "UNVERIFIED"]
DeviationSeverity = Literal["NONE", "MINOR", "MAJOR", "CRITICAL"]


@dataclass(frozen=True)
class DecisionSupportRow:
    requirement: str
    vendor: str
    parameter: str
    required: str
    offered: str
    status: str
    severity: DeviationSeverity
    evidence: str
    claim_status: str
    weight: float
    score_factor: float


@dataclass(frozen=True)
class VendorDecisionSupport:
    vendor: str
    technical_score: float
    evidence_coverage_pct: float
    requirements_checked: int
    compliant_count: int
    deviation_count: int
    major_deviation_count: int
    minor_deviation_count: int
    conflict_count: int
    missing_evidence_count: int
    weighted_requirements: float
    weighted_points: float


def _requirement_weight(requirement_type: str | None) -> float:
    """Weight mandatory requirements above non-mandatory requirements."""
    return 1.0 if (requirement_type or "MANDATORY").strip().upper() == "MANDATORY" else 0.5


def _severity(status: str, requirement_type: str | None, claim_status: str) -> DeviationSeverity:
    normalized_status = status.strip().upper()
    normalized_claim = claim_status.strip().upper()
    if normalized_claim == "CONTRADICTED" or normalized_status == "CONFLICT":
        return "CRITICAL"
    if normalized_status == "DEVIATION":
        return "MAJOR" if _requirement_weight(requirement_type) == 1.0 else "MINOR"
    return "NONE"


def _score_factor(status: str, severity: DeviationSeverity) -> float:
    """Return the auditable technical outcome factor for one requirement."""
    normalized = status.strip().upper()
    if normalized == "COMPLIANT":
        return 1.0
    if normalized == "DEVIATION":
        return 0.25 if severity == "MAJOR" else 0.5
    return 0.0


def build_decision_support(
    requirements: Sequence[Requirement],
    vendor_data: Sequence[VendorValue],
    vendors: Sequence[str] | None = None,
    requirement_types: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build deterministic, auditable vendor decision-support metrics.

    Score formula:
      technical_score = 100 * sum(weight * score_factor) / sum(weight)

    Outcome factors:
      COMPLIANT = 1.00
      mandatory DEVIATION = 0.25
      optional DEVIATION = 0.50
      UNVERIFIED / conflict = 0.00

    Evidence coverage is the share of requirements with explicit quotation
    evidence, independent of whether the value is technically compliant.
    """
    reqs = tuple(requirements)
    type_map = {
        tag.casefold().strip(): value
        for tag, value in (requirement_types or {}).items()
    }
    matrix = build_matrix(reqs, vendor_data, vendors=vendors)

    vendor_names = tuple(dict.fromkeys(
        row["vendor"] for row in matrix
    ))
    summaries: list[VendorDecisionSupport] = []
    detail_rows: list[DecisionSupportRow] = []

    for vendor in vendor_names:
        vendor_rows = [row for row in matrix if row["vendor"] == vendor]
        weighted_total = 0.0
        weighted_points = 0.0
        compliant = deviations = major = minor = conflicts = missing = 0
        evidence_count = 0

        for row in vendor_rows:
            requirement_type = type_map.get(row["requirement"].casefold().strip(), "MANDATORY")
            weight = _requirement_weight(requirement_type)
            severity = _severity(row["status"], requirement_type, row["claim_status"])
            factor = _score_factor(row["status"], severity)
            weighted_total += weight
            weighted_points += weight * factor

            status = row["status"].strip().upper()
            if status == "COMPLIANT":
                compliant += 1
            elif status == "DEVIATION":
                deviations += 1
                if severity == "MAJOR":
                    major += 1
                elif severity == "MINOR":
                    minor += 1
            else:
                if severity == "CRITICAL":
                    conflicts += 1
                else:
                    missing += 1

            if row["offered"] != "MISSING" and row["evidence"].strip():
                evidence_count += 1

            detail_rows.append(
                DecisionSupportRow(
                    requirement=row["requirement"],
                    vendor=vendor,
                    parameter=row["parameter"],
                    required=row["required"],
                    offered=row["offered"],
                    status=status,
                    severity=severity,
                    evidence=row["evidence"],
                    claim_status=row["claim_status"],
                    weight=weight,
                    score_factor=factor,
                )
            )

        requirements_checked = len(vendor_rows)
        coverage = (evidence_count / requirements_checked * 100.0) if requirements_checked else 0.0
        score = (weighted_points / weighted_total * 100.0) if weighted_total else 0.0
        summaries.append(
            VendorDecisionSupport(
                vendor=vendor,
                technical_score=round(score, 2),
                evidence_coverage_pct=round(coverage, 2),
                requirements_checked=requirements_checked,
                compliant_count=compliant,
                deviation_count=deviations,
                major_deviation_count=major,
                minor_deviation_count=minor,
                conflict_count=conflicts,
                missing_evidence_count=missing,
                weighted_requirements=round(weighted_total, 4),
                weighted_points=round(weighted_points, 4),
            )
        )

    summaries.sort(key=lambda item: (-item.technical_score, item.vendor.casefold()))
    return {
        "formula": {
            "technical_score": "100 * weighted_points / weighted_requirements",
            "weights": {
                "MANDATORY": 1.0,
                "NON_MANDATORY": 0.5,
            },
            "outcome_factors": {
                "COMPLIANT": 1.0,
                "MANDATORY_DEVIATION": 0.25,
                "OPTIONAL_DEVIATION": 0.5,
                "UNVERIFIED": 0.0,
                "CONFLICT": 0.0,
            },
            "evidence_coverage": "100 * requirements with explicit evidence / requirements checked",
        },
        "vendors": [
            {
                "vendor": item.vendor,
                "technical_score": item.technical_score,
                "evidence_coverage_pct": item.evidence_coverage_pct,
                "requirements_checked": item.requirements_checked,
                "compliant_count": item.compliant_count,
                "deviation_count": item.deviation_count,
                "major_deviation_count": item.major_deviation_count,
                "minor_deviation_count": item.minor_deviation_count,
                "conflict_count": item.conflict_count,
                "missing_evidence_count": item.missing_evidence_count,
                "weighted_requirements": item.weighted_requirements,
                "weighted_points": item.weighted_points,
            }
            for item in summaries
        ],
        "rows": [
            {
                "requirement": row.requirement,
                "vendor": row.vendor,
                "parameter": row.parameter,
                "required": row.required,
                "offered": row.offered,
                "status": row.status,
                "severity": row.severity,
                "evidence": row.evidence,
                "claim_status": row.claim_status,
                "weight": row.weight,
                "score_factor": row.score_factor,
            }
            for row in detail_rows
        ],
    }
