"""Lifecycle intelligence read models over canonical asset and event records."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import AssetProduct, LifecycleEvent, ProcurementPackage, Project, User, get_db

router = APIRouter(tags=["lifecycle"])


class LifecycleAssetSummary(BaseModel):
    asset_id: str
    package_id: int
    offer_id: int | None
    manufacturer: str | None
    model: str | None
    part_number: str | None
    serial_number: str | None
    status: str
    event_count: int
    failure_count: int
    maintenance_count: int
    warranty_event_count: int
    spare_part_count: int
    replacement_count: int
    first_event_date: datetime | None
    latest_event_date: datetime | None


class LifecycleIntelligenceResponse(BaseModel):
    organization_id: int
    asset_count: int
    event_count: int
    event_counts_by_type: dict[str, int]
    assets: list[LifecycleAssetSummary]


def _member(db: Session, user: User, organization_id: int) -> None:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")


def _build(db: Session, organization_id: int, assets: list[AssetProduct]) -> LifecycleIntelligenceResponse:
    package_ids = [a.package_id for a in assets]
    events = []
    if package_ids:
        events = list(db.scalars(select(LifecycleEvent).where(LifecycleEvent.package_id.in_(package_ids))).all())
    by_asset: dict[str, list[LifecycleEvent]] = {}
    for event in events:
        by_asset.setdefault(event.asset_id, []).append(event)
    summaries = []
    for asset in sorted(assets, key=lambda item: item.asset_id):
        asset_events = sorted(by_asset.get(asset.asset_id, []), key=lambda item: (item.event_date, item.id))
        counts = Counter(event.event_type for event in asset_events)
        summaries.append(
            LifecycleAssetSummary(
                asset_id=asset.asset_id,
                package_id=asset.package_id,
                offer_id=asset.offer_id,
                manufacturer=asset.manufacturer,
                model=asset.model,
                part_number=asset.part_number,
                serial_number=asset.serial_number,
                status=asset.status,
                event_count=len(asset_events),
                failure_count=counts.get("FAILURE", 0),
                maintenance_count=counts.get("MAINTENANCE", 0),
                warranty_event_count=counts.get("WARRANTY", 0),
                spare_part_count=counts.get("SPARE_PART", 0),
                replacement_count=counts.get("REPLACEMENT", 0),
                first_event_date=asset_events[0].event_date if asset_events else None,
                latest_event_date=asset_events[-1].event_date if asset_events else None,
            )
        )
    return LifecycleIntelligenceResponse(
        organization_id=organization_id,
        asset_count=len(assets),
        event_count=len(events),
        event_counts_by_type=dict(sorted(Counter(event.event_type for event in events).items())),
        assets=summaries,
    )


@router.get("/organizations/{organization_id}/lifecycle-intelligence", response_model=LifecycleIntelligenceResponse)
def organization_lifecycle_intelligence(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> LifecycleIntelligenceResponse:
    _member(db, user, organization_id)
    assets = list(
        db.scalars(
            select(AssetProduct)
            .join(ProcurementPackage, AssetProduct.package_id == ProcurementPackage.id)
            .join(Project, ProcurementPackage.project_id == Project.id)
            .where(Project.organization_id == organization_id)
        ).all()
    )
    return _build(db, organization_id, assets)


@router.get("/packages/{package_id}/lifecycle-intelligence", response_model=LifecycleIntelligenceResponse)
def package_lifecycle_intelligence(
    package_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> LifecycleIntelligenceResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    assets = list(db.scalars(select(AssetProduct).where(AssetProduct.package_id == package_id)).all())
    return _build(db, package.project.organization_id, assets)
