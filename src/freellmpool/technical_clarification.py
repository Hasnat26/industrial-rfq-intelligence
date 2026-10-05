"""Technical clarification and vendor resubmission decision-support helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class TechnicalGap:
    """One vendor-specific technical information gap requiring clarification."""

    parameter: str
    required: str
    offered: str | None
    status: str
    request: str


@dataclass(frozen=True)
class TechnicalClarificationPackage:
    """Customer-ready clarification list and email draft for one vendor."""

    vendor: str
    technical_revision: str
    gaps: tuple[TechnicalGap, ...]
    subject: str
    body: str


def build_technical_clarification_package(
    vendor: str,
    technical_revision: str,
    rows: Sequence[dict[str, object]],
) -> TechnicalClarificationPackage:
    """Build a deterministic clarification request from technical comparison rows.

    UNVERIFIED means the vendor did not provide a usable claim/evidence for the
    requirement. DEVIATION means a claim exists but differs from the RFQ.
    COMPLIANT rows are intentionally excluded.
    """
    gaps: list[TechnicalGap] = []
    for row in rows:
        status = str(row.get("status", "")).strip().upper()
        if status not in {"UNVERIFIED", "DEVIATION"}:
            continue
        parameter = str(row.get("parameter", "")).strip()
        required = str(row.get("required", "")).strip()
        offered_raw = row.get("offered")
        offered = None if offered_raw is None else str(offered_raw).strip() or None
        if not parameter or not required:
            continue
        if status == "UNVERIFIED":
            request = (
                f"Please confirm the offered value for {parameter!r} against the "
                f"required value {required!r} and provide the relevant technical "
                "datasheet/quotation reference as evidence."
            )
        else:
            request = (
                f"Your offer states {offered or 'a different value'} for "
                f"{parameter!r}, while the RFQ requires {required!r}. Please "
                "confirm the deviation, proposed alternative, and compliance "
                "basis, or submit a revised compliant offer."
            )
        gaps.append(
            TechnicalGap(
                parameter=parameter,
                required=required,
                offered=offered,
                status=status,
                request=request,
            )
        )

    gaps = sorted(gaps, key=lambda item: (item.parameter.casefold(), item.status))
    subject = f"Technical Clarification Required – RFQ Offer – {vendor}"
    lines = [
        f"Dear {vendor} Team,",
        "",
        "Thank you for your technical offer.",
        "",
        "During our technical evaluation against the RFQ requirements, we identified "
        "the following items that are missing, unclear, or require deviation "
        "clarification:",
        "",
    ]
    for index, gap in enumerate(gaps, start=1):
        lines.extend(
            [
                f"{index}. {gap.parameter}",
                f"   RFQ requirement: {gap.required}",
                f"   Vendor offer: {gap.offered or 'Not stated / no verifiable evidence'}",
                f"   Required action: {gap.request}",
                "",
            ]
        )
    lines.extend(
        [
            "Please provide the missing/clarifying information and, where applicable, "
            "submit a revised technical offer reflecting the requested information.",
            "Please keep the technical revision clearly identified so that we can "
            "update our evaluation record.",
            "",
            "Best regards,",
            "Procurement / Engineering Team",
        ]
    )
    return TechnicalClarificationPackage(
        vendor=vendor,
        technical_revision=technical_revision,
        gaps=tuple(gaps),
        subject=subject,
        body="\n".join(lines),
    )


def clarification_rows_for_vendor(
    rows: Sequence[object],
    vendor: str,
) -> list[dict[str, object]]:
    """Filter API comparison rows for one vendor into engine input dictionaries."""
    selected: list[dict[str, object]] = []
    vendor_key = vendor.casefold().strip()
    for item in rows:
        if isinstance(item, dict):
            row = item
        else:
            row = {
                "vendor": getattr(item, "vendor", None),
                "parameter": getattr(item, "parameter", None),
                "required": getattr(item, "required", None),
                "offered": getattr(item, "offered", None),
                "status": getattr(item, "status", None),
            }
        if str(row.get("vendor", "")).casefold().strip() == vendor_key:
            selected.append(row)
    return selected
