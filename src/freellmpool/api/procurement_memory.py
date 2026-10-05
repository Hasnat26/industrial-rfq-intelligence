"""Historical procurement-memory read model built from canonical procurement records.

P3 deliberately starts as a projection over the existing procurement ledger. It does
not duplicate vendor, offer, decision, or evidence data; historical intelligence is
derived from the authoritative records already stored by the workflow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import (
    ProcurementDecision,
    ProcurementPackage,
    Project,
    User,
    VendorOffer,
    get_db,
)

router = APIRouter()


class MemoryEvidence(BaseModel):
    claim_id: int
    parameter: str
    value: str
    evidence: str
    claim_status: str
    source_document_id: int | None
    source_page: int | None
    source_section: str | None
    source_table: str | None
    source_cell: str | None


class ProcurementMemoryEntry(BaseModel):
    package_id: int
    project_id: int
    project_name: str
    package_name: str
    category: str
    vendor_name: str
    technical_revision: str
    technical_status: str
    price: str | None
    currency: str | None
    lead_time: str | None
    warranty: str | None
    selected_for_purchase: bool
    decision_rationale: str | None
    evidence: list[MemoryEvidence]


class ProcurementMemoryResponse(BaseModel):
    organization_id: int
    query: str | None
    vendor: str | None
    category: str | None
    total: int
    entries: list[ProcurementMemoryEntry]


def _memory_entries(
    db: Session,
    organization_id: int,
    *,
    package_id: int | None = None,
    query: str | None = None,
    vendor: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[ProcurementMemoryEntry]:
    packages = db.scalars(
        select(ProcurementPackage)
        .join(Project)
        .where(Project.organization_id == organization_id)
        .order_by(ProcurementPackage.id)
    ).all()
    if package_id is not None:
        packages = [item for item in packages if item.id == package_id]

    normalized_query = (query or "").strip().casefold()
    normalized_vendor = (vendor or "").strip().casefold()
    normalized_category = (category or "").strip().casefold()
    entries: list[ProcurementMemoryEntry] = []

    for package in packages:
        project = package.project
        decision = db.scalar(
            select(ProcurementDecision).where(ProcurementDecision.package_id == package.id)
        )
        selected_offer_id = decision.selected_offer_id if decision is not None else None

        for offer in sorted(package.offers, key=lambda item: item.id):
            if normalized_vendor and normalized_vendor not in offer.vendor_name.casefold():
                continue
            if normalized_category and normalized_category != package.category.casefold():
                continue

            evidence = [
                MemoryEvidence(
                    claim_id=claim.id,
                    parameter=claim.parameter,
                    value=claim.value,
                    evidence=claim.evidence,
                    claim_status=claim.claim_status,
                    source_document_id=claim.source_document_id,
                    source_page=claim.source_page,
                    source_section=claim.source_section,
                    source_table=claim.source_table,
                    source_cell=claim.source_cell,
                )
                for claim in offer.claims
            ]
            searchable = " ".join(
                [
                    package.name,
                    package.category,
                    project.name,
                    offer.vendor_name,
                    offer.technical_revision,
                    offer.technical_status,
                    offer.price or "",
                    offer.currency or "",
                    offer.lead_time or "",
                    offer.warranty or "",
                    decision.rationale if decision is not None else "",
                    *(f"{item.parameter} {item.value} {item.evidence}" for item in evidence),
                ]
            ).casefold()
            if normalized_query and normalized_query not in searchable:
                continue

            entries.append(
                ProcurementMemoryEntry(
                    package_id=package.id,
                    project_id=project.id,
                    project_name=project.name,
                    package_name=package.name,
                    category=package.category,
                    vendor_name=offer.vendor_name,
                    technical_revision=offer.technical_revision,
                    technical_status=offer.technical_status,
                    price=offer.price,
                    currency=offer.currency,
                    lead_time=offer.lead_time,
                    warranty=offer.warranty,
                    selected_for_purchase=selected_offer_id == offer.id,
                    decision_rationale=decision.rationale if decision is not None else None,
                    evidence=evidence,
                )
            )
            if len(entries) >= limit:
                return entries
    return entries


@router.get(
    "/organizations/{organization_id}/procurement-memory",
    response_model=ProcurementMemoryResponse,
)
def procurement_memory(
    organization_id: int,
    query: str | None = Query(default=None, max_length=200),
    vendor: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=100),
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementMemoryResponse:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    entries = _memory_entries(
        db,
        organization_id,
        query=query,
        vendor=vendor,
        category=category,
        limit=limit,
    )
    return ProcurementMemoryResponse(
        organization_id=organization_id,
        query=query,
        vendor=vendor,
        category=category,
        total=len(entries),
        entries=entries,
    )


@router.get(
    "/packages/{package_id}/memory",
    response_model=ProcurementMemoryResponse,
)
def package_memory(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementMemoryResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    entries = _memory_entries(db, package.project.organization_id, package_id=package_id)
    return ProcurementMemoryResponse(
        organization_id=package.project.organization_id,
        query=None,
        vendor=None,
        category=None,
        total=len(entries),
        entries=entries,
    )
