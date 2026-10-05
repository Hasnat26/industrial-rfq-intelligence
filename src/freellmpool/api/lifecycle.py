"""Tenant-isolated lifecycle event API for post-procurement intelligence."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import (
    LifecycleEvent,
    ProcurementPackage,
    Project,
    User,
    VendorOffer,
    get_db,
)
from freellmpool.api.schemas import LifecycleEventCreate, LifecycleEventRead
from freellmpool.procurement_domain import LifecycleEventType

router = APIRouter(tags=["lifecycle"])


def _package_for_user(db: Session, package_id: int, user: User) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    project = package.project
    if project is None or not is_member(db, user.id, project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    return package


def _validate_event_type(value: str) -> str:
    try:
        return LifecycleEventType(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LifecycleEventType)
        raise HTTPException(
            status_code=422,
            detail=f"unsupported lifecycle event type; expected one of: {allowed}",
        ) from exc


@router.post(
    "/packages/{package_id}/lifecycle-events",
    response_model=LifecycleEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lifecycle_event(
    package_id: int,
    payload: LifecycleEventCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> LifecycleEvent:
    package = _package_for_user(db, package_id, user)
    event_type = _validate_event_type(payload.event_type)
    if payload.offer_id is not None:
        offer = db.get(VendorOffer, payload.offer_id)
        if offer is None or offer.package_id != package.id:
            raise HTTPException(status_code=422, detail="offer does not belong to package")
    event = LifecycleEvent(
        package_id=package.id,
        offer_id=payload.offer_id,
        asset_id=payload.asset_id.strip(),
        event_type=event_type,
        event_date=payload.event_date,
        description=payload.description.strip(),
        evidence=payload.evidence,
        created_by_user_id=user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get(
    "/packages/{package_id}/lifecycle-events",
    response_model=list[LifecycleEventRead],
)
def list_lifecycle_events(
    package_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LifecycleEvent]:
    package = _package_for_user(db, package_id, user)
    return list(
        db.scalars(
            select(LifecycleEvent)
            .where(LifecycleEvent.package_id == package.id)
            .order_by(LifecycleEvent.event_date.asc(), LifecycleEvent.id.asc())
        ).all()
    )


@router.get(
    "/organizations/{organization_id}/lifecycle-events",
    response_model=list[LifecycleEventRead],
)
def list_organization_lifecycle_events(
    organization_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LifecycleEvent]:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return list(
        db.scalars(
            select(LifecycleEvent)
            .join(ProcurementPackage, LifecycleEvent.package_id == ProcurementPackage.id)
            .join(Project, ProcurementPackage.project_id == Project.id)
            .where(Project.organization_id == organization_id)
        ).all()
    )
