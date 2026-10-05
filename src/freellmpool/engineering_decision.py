"""Auditable engineering decision summaries built from deterministic RFQ metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict


class VendorDispositionPayload(TypedDict):
    vendor: str
    disposition: str
    rationale: list[str]
    technical_score: float
    evidence_coverage_pct: float
    compliant_count: int
    deviation_count: int
    major_deviation_count: int
    minor_deviation_count: int
    conflict_count: int
    missing_evidence_count: int


class EngineeringDecisionSummaryPayload(TypedDict):
    status: str
    decision_basis: list[str]
    vendor_profiles: list[VendorDispositionPayload]
    review_actions: list[str]


@dataclass(frozen=True)
class _VendorMetrics:
    vendor: str
    technical_score: float
    evidence_coverage_pct: float
    compliant_count: int
    deviation_count: int
    major_deviation_count: int
    minor_deviation_count: int
    conflict_count: int
    missing_evidence_count: int


def _metric(item: Mapping[str, object], key: str) -> float:
    value = item.get(key, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _int_metric(item: Mapping[str, object], key: str) -> int:
    return int(_metric(item, key))


def build_engineering_decision_summary(
    vendors: Sequence[Mapping[str, object]],
) -> EngineeringDecisionSummaryPayload:
    """Produce a deterministic engineering disposition without selecting a supplier."""
    metrics = [
        _VendorMetrics(
            vendor=str(item.get("vendor", "")),
            technical_score=_metric(item, "technical_score"),
            evidence_coverage_pct=_metric(item, "evidence_coverage_pct"),
            compliant_count=_int_metric(item, "compliant_count"),
            deviation_count=_int_metric(item, "deviation_count"),
            major_deviation_count=_int_metric(item, "major_deviation_count"),
            minor_deviation_count=_int_metric(item, "minor_deviation_count"),
            conflict_count=_int_metric(item, "conflict_count"),
            missing_evidence_count=_int_metric(item, "missing_evidence_count"),
        )
        for item in vendors
    ]

    profiles: list[VendorDispositionPayload] = []
    review_actions: list[str] = []

    for item in metrics:
        rationale: list[str] = []
        if item.conflict_count:
            disposition = "CRITICAL_CONFLICT_REVIEW"
            rationale.append(f"{item.conflict_count} conflicting requirement claim(s) require resolution.")
            review_actions.append(f"{item.vendor}: resolve {item.conflict_count} conflicting claim(s) before technical acceptance.")
        elif item.major_deviation_count:
            disposition = "MAJOR_DEVIATION_REVIEW"
            rationale.append(f"{item.major_deviation_count} mandatory requirement deviation(s) require engineering review.")
            review_actions.append(f"{item.vendor}: review {item.major_deviation_count} major deviation(s).")
        elif item.missing_evidence_count:
            disposition = "EVIDENCE_COMPLETION_REQUIRED"
            rationale.append(f"{item.missing_evidence_count} requirement(s) lack sufficient quotation evidence.")
            review_actions.append(f"{item.vendor}: obtain evidence for {item.missing_evidence_count} unverified requirement(s).")
        elif item.minor_deviation_count:
            disposition = "MINOR_DEVIATION_REVIEW"
            rationale.append(f"{item.minor_deviation_count} optional requirement deviation(s) require review.")
            review_actions.append(f"{item.vendor}: confirm {item.minor_deviation_count} minor deviation(s).")
        else:
            disposition = "TECHNICALLY_COMPLIANT_PROFILE"
            rationale.append("All checked requirements have explicit evidence and no detected deviation or conflict.")

        rationale.append(f"Technical score: {item.technical_score:.2f}/100.")
        rationale.append(f"Evidence coverage: {item.evidence_coverage_pct:.2f}%.")

        profiles.append(
            {
                "vendor": item.vendor,
                "disposition": disposition,
                "rationale": rationale,
                "technical_score": item.technical_score,
                "evidence_coverage_pct": item.evidence_coverage_pct,
                "compliant_count": item.compliant_count,
                "deviation_count": item.deviation_count,
                "major_deviation_count": item.major_deviation_count,
                "minor_deviation_count": item.minor_deviation_count,
                "conflict_count": item.conflict_count,
                "missing_evidence_count": item.missing_evidence_count,
            }
        )

    if not metrics:
        status = "INSUFFICIENT_VENDOR_DATA"
        decision_basis = ["No vendor profiles are available for engineering review."]
    elif any(item.conflict_count or item.major_deviation_count for item in metrics):
        status = "ENGINEERING_REVIEW_REQUIRED"
        decision_basis = [
            "At least one vendor has a conflict or major deviation.",
            "Supplier selection remains outside the deterministic technical decision-support layer.",
        ]
    elif any(item.missing_evidence_count or item.minor_deviation_count for item in metrics):
        status = "EVIDENCE_OR_DEVIATION_REVIEW_REQUIRED"
        decision_basis = [
            "At least one vendor requires evidence completion or deviation review.",
            "Supplier selection remains outside the deterministic technical decision-support layer.",
        ]
    else:
        status = "TECHNICAL_PROFILES_READY_FOR_COMMERCIAL_REVIEW"
        decision_basis = [
            "All vendor profiles have complete evidence with no detected deviation or conflict.",
            "The technical layer does not autonomously select a supplier.",
        ]

    return {
        "status": status,
        "decision_basis": decision_basis,
        "vendor_profiles": profiles,
        "review_actions": review_actions,
    }


__all__ = ["build_engineering_decision_summary"]
