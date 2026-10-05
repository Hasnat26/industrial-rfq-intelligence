"""Tenant-isolated lifecycle cost inputs and summaries."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import (\n    LifecycleCostRecord,\n    LifecycleEvent,\n    ProcurementPackage,\n    Project,\n    User,\n    get_db,\n)
from freellmpool.api.schemas import LifecycleCostCreate, LifecycleCostRead

router = APIRouter(tags=["lifecycle"])


def _package_for_user(db: Session, package_id: int, user: User) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    return package


@router.post(
    "/packages/{package_id}/lifecycle-costs",
    response_model=LifecycleCostRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lifecycle_cost(
    package_id: int,
    payload: LifecycleCostCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> LifecycleCostRecord:
    package = _package_for_user(db, package_id, user)
    asset_id = payload.asset_id.strip()
    if payload.event_id is not None:
        event = db.get(LifecycleEvent, payload.event_id)
        if event is None or event.package_id != package.id or event.asset_id != asset_id:
            raise HTTPException(status_code=422, detail="event does not belong to asset and package")
    record = LifecycleCostRecord(
        package_id=package.id,
        created_by_user_id=user.id,
        **payload.model_dump(exclude={"asset_id"}),
        asset_id=asset_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/packages/{package_id}/lifecycle-costs", response_model=list[LifecycleCostRead])
def list_lifecycle_costs(
    package_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[LifecycleCostRecord]:
    package = _package_for_user(db, package_id, user)
    return list(
        db.scalars(
            select(LifecycleCostRecord)
            .where(LifecycleCostRecord.package_id == package.id)
            .order_by(LifecycleCostRecord.cost_date, LifecycleCostRecord.id)
        ).all()
    )


@router.get("/organizations/{organization_id}/lifecycle-cost-summary")
def lifecycle_cost_summary(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> dict:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    rows = list(
        db.execute(
            select(LifecycleCostRecord)
            .join(ProcurementPackage, LifecycleCostRecord.package_id == ProcurementPackage.id)
            .join(Project, ProcurementPackage.project_id == Project.id)
            .where(Project.organization_id == organization_id)
        ).scalars()
    )
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        totals[row.asset_id][row.currency] += row.amount
    return {
        "organization_id": organization_id,
        "record_count": len(rows),
        "totals_by_asset_currency": {
            asset: dict(sorted(currencies.items())) for asset, currencies in sorted(totals.items())
        },
    }
