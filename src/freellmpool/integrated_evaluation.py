"""Deterministic integrated technical-commercial evaluation for RFQs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict


class IntegratedVendorPayload(TypedDict):
    vendor: str
    technical_score: float
    commercial_score: float
    integrated_score: float
    evidence_coverage_pct: float
    commercial_flags: list[str]
    technical_gate: str
    commercial_gate: str
    disposition: str
    price: float | None
    currency: str
    lead_time_weeks: float | None
    warranty_months: float | None


class IntegratedEvaluationPayload(TypedDict):
    status: str
    formula: dict[str, object]
    decision_note: str
    vendor_profiles: list[IntegratedVendorPayload]
    review_actions: list[str]


@dataclass(frozen=True)
class _Commercial:
    vendor: str
    price: float | None
    currency: str
    lead_time_weeks: float | None
    warranty_months: float | None
    payment_terms: str
    flags: tuple[str, ...]


def _number(item: Mapping[str, object], key: str) -> float | None:
    value = item.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _commercial_score(
    item: _Commercial,
    comparable: Sequence[_Commercial],
) -> float:
    """Score only comparable numeric commercial facts; missing facts score zero."""
    prices = [x.price for x in comparable if x.price is not None]
    leads = [x.lead_time_weeks for x in comparable if x.lead_time_weeks is not None]
    warranties = [x.warranty_months for x in comparable if x.warranty_months is not None]
    factors: list[float] = []

    if item.price is not None and prices and min(prices) > 0:
        factors.append(min(prices) / item.price * 100.0)
    else:
        factors.append(0.0)

    if item.lead_time_weeks is not None and leads and min(leads) >= 0:
        factors.append((min(leads) / item.lead_time_weeks * 100.0) if item.lead_time_weeks > 0 else 100.0)
    else:
        factors.append(0.0)

    if item.warranty_months is not None and warranties and max(warranties) > 0:
        factors.append(item.warranty_months / max(warranties) * 100.0)
    else:
        factors.append(0.0)

    factors.append(100.0 if item.payment_terms.strip() else 0.0)
    return round(sum(factors) / len(factors), 2)


def build_integrated_evaluation(
    technical_vendors: Sequence[Mapping[str, object]],
    commercial_rows: Sequence[Mapping[str, object]],
) -> IntegratedEvaluationPayload:
    """Combine deterministic technical and commercial metrics without selecting a supplier."""
    commercial = [
        _Commercial(
            vendor=str(item.get("vendor", "")),
            price=_number(item, "price"),
            currency=str(item.get("currency", "")).strip().upper(),
            lead_time_weeks=_number(item, "lead_time_weeks"),
            warranty_months=_number(item, "warranty_months"),
            payment_terms=str(item.get("payment_terms", "")),
            flags=tuple(str(flag) for flag in item.get("flags", []) if isinstance(flag, str)),
        )
        for item in commercial_rows
    ]
    by_vendor = {item.vendor: item for item in commercial}
    currencies = {item.currency for item in commercial if item.currency}
    currency_comparable = len(currencies) <= 1

    comparable = tuple(
        item for item in commercial
        if currency_comparable and item.currency in currencies
    )

    profiles: list[IntegratedVendorPayload] = []
    review_actions: list[str] = []

    for technical in technical_vendors:
        vendor = str(technical.get("vendor", ""))
        commercial_item = by_vendor.get(vendor, _Commercial(vendor, None, "", None, None, "", ("COMMERCIAL_DATA_MISSING",)))
        technical_score = float(technical.get("technical_score", 0.0))
        commercial_score = _commercial_score(commercial_item, comparable) if commercial_item.currency or commercial_item.price is not None else 0.0
        integrated_score = round(technical_score * 0.70 + commercial_score * 0.30, 2)

        technical_gate = "BLOCKED" if (
            int(technical.get("conflict_count", 0) or 0) > 0
            or int(technical.get("major_deviation_count", 0) or 0) > 0
            or int(technical.get("missing_evidence_count", 0) or 0) > 0
        ) else "PASS"
        commercial_gate = "REVIEW" if commercial_item.flags or not currency_comparable else "PASS"

        if technical_gate == "BLOCKED":
            disposition = "TECHNICAL_REVIEW_REQUIRED"
            review_actions.append(f"{vendor}: complete technical evidence/deviation review before commercial decision.")
        elif commercial_gate == "REVIEW":
            disposition = "COMMERCIAL_REVIEW_REQUIRED"
            review_actions.append(f"{vendor}: resolve commercial flags before integrated evaluation can be used for human selection.")
        else:
            disposition = "READY_FOR_HUMAN_SELECTION"

        profiles.append(
            {
                "vendor": vendor,
                "technical_score": technical_score,
                "commercial_score": commercial_score,
                "integrated_score": integrated_score,
                "evidence_coverage_pct": float(technical.get("evidence_coverage_pct", 0.0) or 0.0),
                "commercial_flags": list(commercial_item.flags),
                "technical_gate": technical_gate,
                "commercial_gate": commercial_gate,
                "disposition": disposition,
                "price": commercial_item.price,
                "currency": commercial_item.currency,
                "lead_time_weeks": commercial_item.lead_time_weeks,
                "warranty_months": commercial_item.warranty_months,
            }
        )

    profiles.sort(key=lambda item: (-item["integrated_score"], item["vendor"].casefold()))
    if not profiles:
        status = "INSUFFICIENT_VENDOR_DATA"
        decision_note = "No vendor profile is available for integrated evaluation."
    elif not currency_comparable:
        status = "COMMERCIAL_COMPARABILITY_REVIEW_REQUIRED"
        decision_note = "Commercial scores are withheld as comparable prices are not expressed in one currency."
    elif any(item["technical_gate"] == "BLOCKED" for item in profiles):
        status = "TECHNICAL_REVIEW_REQUIRED"
        decision_note = "Technical gates must be resolved before integrated commercial comparison can support human selection."
    elif any(item["commercial_gate"] == "REVIEW" for item in profiles):
        status = "COMMERCIAL_REVIEW_REQUIRED"
        decision_note = "Commercial exception flags must be resolved before human supplier selection."
    else:
        status = "READY_FOR_HUMAN_SELECTION"
        decision_note = "All evaluated vendors passed deterministic technical and commercial gates; no supplier is selected automatically."

    return {
        "status": status,
        "formula": {
            "integrated_score": "0.70 * technical_score + 0.30 * commercial_score",
            "commercial_score": "average(price, lead_time, warranty, payment_terms factors)",
            "commercial_factors": {
                "price": "100 * minimum comparable price / vendor price",
                "lead_time": "100 * minimum comparable lead time / vendor lead time",
                "warranty": "100 * vendor warranty / maximum comparable warranty",
                "payment_terms": "100 when terms are explicitly present, otherwise 0",
            },
            "control": "Commercial scores are not compared across currencies.",
        },
        "decision_note": decision_note,
        "vendor_profiles": profiles,
        "review_actions": review_actions,
    }


__all__ = ["build_integrated_evaluation"]
