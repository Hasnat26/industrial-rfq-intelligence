"""Canonical domain models for the industrial procurement SaaS roadmap.

These models are storage-agnostic. They define the business objects and workflow
states that the future web/database layer will persist around the existing
engineering intelligence core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProcurementMode(StrEnum):
    STANDARD = "STANDARD"
    PROJECT_EPC = "PROJECT_EPC"


class RequirementType(StrEnum):
    MANDATORY = "MANDATORY"
    PREFERRED = "PREFERRED"
    OPTIONAL = "OPTIONAL"


class TechnicalStatus(StrEnum):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_DEVIATION = "ACCEPTED_WITH_DEVIATION"
    REJECTED = "REJECTED"


class CommercialStatus(StrEnum):
    LOCKED = "LOCKED"
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"


class LifecycleEventType(StrEnum):
    PURCHASE = "PURCHASE"
    DELIVERY = "DELIVERY"
    INSTALLATION = "INSTALLATION"
    COMMISSIONING = "COMMISSIONING"
    PERFORMANCE = "PERFORMANCE"
    WARRANTY = "WARRANTY"
    MAINTENANCE = "MAINTENANCE"
    FAILURE = "FAILURE"
    SPARE_PART = "SPARE_PART"
    REPLACEMENT = "REPLACEMENT"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ProcurementRequirement:
    tag: str
    parameter: str
    required_value: str
    unit: str | None = None
    requirement_type: RequirementType = RequirementType.MANDATORY
    acceptance_rule: str | None = None
    evidence_id: str | None = None


@dataclass
class TechnicalOfferRecord:
    vendor_id: str
    revision: str
    status: TechnicalStatus = TechnicalStatus.PENDING
    document_refs: list[str] = field(default_factory=list)
    clarification_ids: list[str] = field(default_factory=list)
    deviation_ids: list[str] = field(default_factory=list)


@dataclass
class CommercialOfferRecord:
    vendor_id: str
    technical_offer_revision: str
    price: str
    currency: str
    lead_time: str
    warranty: str
    payment_terms: str
    status: CommercialStatus = CommercialStatus.LOCKED
    evidence_id: str | None = None


@dataclass
class ProcurementPackageRecord:
    package_id: str
    category: str
    mode: ProcurementMode
    requirements: list[ProcurementRequirement] = field(default_factory=list)
    technical_offers: list[TechnicalOfferRecord] = field(default_factory=list)
    commercial_offers: list[CommercialOfferRecord] = field(default_factory=list)
    technical_bid_locked: bool = False
    commercial_evaluation_completed: bool = False

    def open_commercial_evaluation(self) -> None:
        """Open commercial evaluation only after a technical-bid lock."""
        if self.mode == ProcurementMode.PROJECT_EPC and not self.technical_bid_locked:
            raise ValueError(
                "commercial evaluation cannot open before technical bid lock"
            )
        for offer in self.commercial_offers:
            offer.status = CommercialStatus.OPEN

    def lock_technical_bid(self) -> None:
        """Lock the technical stage for project/EPC commercial opening."""
        self.technical_bid_locked = True


@dataclass(frozen=True)
class LifecycleRecord:
    asset_id: str
    event_type: LifecycleEventType
    event_date: str
    description: str
    evidence_id: str | None = None


@dataclass(frozen=True)
class ProcurementMemoryRecord:
    organization_id: str
    category: str
    manufacturer: str | None
    model: str | None
    vendor_id: str | None
    project_id: str | None
    decision_rationale: str | None
    technical_basis: str | None
    commercial_basis: str | None
    lifecycle_records: tuple[LifecycleRecord, ...] = ()

__all__ = [
    "CommercialOfferRecord",
    "CommercialStatus",
    "LifecycleEventType",
    "LifecycleRecord",
    "ProcurementMemoryRecord",
    "ProcurementMode",
    "ProcurementPackageRecord",
    "ProcurementRequirement",
    "RequirementType",
    "TechnicalOfferRecord",
    "TechnicalStatus",
]
