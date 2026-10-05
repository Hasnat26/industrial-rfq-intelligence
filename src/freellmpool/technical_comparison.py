"""Deterministic technical comparison and vendor-specific gap classification."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from freellmpool.industrial import Requirement, VendorValue, build_matrix


@dataclass(frozen=True)
class TechnicalFinding:
    """One requirement/vendor finding from the deterministic comparison."""

    requirement: str
    vendor: str
    parameter: str
    required: str
    offered: str | None
    status: str
    gap_type: str | None
    evidence: str
    claim_status: str


def compare_technical_requirements(
    requirements: Sequence[Requirement],
    vendor_values: Sequence[VendorValue],
    vendors: Sequence[str],
) -> list[TechnicalFinding]:
    """Compare every vendor against every requirement and fail closed on uncertainty.

    Existing build_matrix remains the compatibility engine for the legacy
    comparison endpoint. This Block 1 boundary adds explicit gap semantics and
    ensures a non-verified claim cannot become COMPLIANT merely because its
    value happens to equal the requirement.
    """
    matrix = build_matrix(requirements, vendor_values, vendors=vendors)
    claims_by_key: dict[tuple[str, str], list[VendorValue]] = {}
    for claim in vendor_values:
        key = (claim.vendor.casefold().strip(), claim.parameter.casefold().strip())
        claims_by_key.setdefault(key, []).append(claim)

    findings: list[TechnicalFinding] = []
    for row in matrix:
        vendor = row["vendor"]
        parameter = row["parameter"]
        key = (vendor.casefold().strip(), parameter.casefold().strip())
        claims = claims_by_key.get(key, [])

        status = row["status"]
        gap_type: str | None = None
        if not claims:
            status = "UNVERIFIED"
            gap_type = "MISSING"
        elif any(claim.claim_status == "CONTRADICTED" for claim in claims):
            status = "UNVERIFIED"
            gap_type = "CONFLICT"
        elif len({claim.value.strip().casefold() for claim in claims}) > 1:
            status = "UNVERIFIED"
            gap_type = "CONFLICT"
        elif any(claim.claim_status != "VERIFIED" for claim in claims):
            status = "UNVERIFIED"
            gap_type = "EVIDENCE_REQUIRED"
        elif status == "DEVIATION":
            gap_type = "DEVIATION"

        offered = row["offered"]
        findings.append(
            TechnicalFinding(
                requirement=row["requirement"],
                vendor=vendor,
                parameter=parameter,
                required=row["required"],
                offered=None if offered in {"MISSING", "CONFLICTING"} else offered,
                status=status,
                gap_type=gap_type,
                evidence=row["evidence"],
                claim_status=row["claim_status"],
            )
        )
    return findings
