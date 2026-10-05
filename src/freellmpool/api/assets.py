"""Tenant-isolated installed asset lifecycle records."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import AssetProduct, ProcurementPackage, Project, User, VendorOffer, get_db
from freellmpool.api.schemas import AssetProductCreate, AssetProductRead

router = APIRouter(tags=["lifecycle"])


def _package_for_user(db: Session, package_id: int, user: User) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    return package


@router.post(
    "/packages/{package_id}/assets",
    response_model=AssetProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_asset(
    package_id: int,
    payload: AssetProductCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> AssetProduct:
    package = _package_for_user(db, package_id, user)
    if payload.offer_id is not None:
        offer = db.get(VendorOffer, payload.offer_id)
        if offer is None or offer.package_id != package.id:
            raise HTTPException(status_code=422, detail="offer does not belong to package")
    existing = db.scalar(
        select(AssetProduct).where(
            AssetProduct.package_id == package.id,
            AssetProduct.asset_id == payload.asset_id.strip(),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="asset already exists for package")
    asset = AssetProduct(package_id=package.id, **payload.model_dump(exclude={"asset_id"}), asset_id=payload.asset_id.strip())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get(
    "/packages/{package_id}/assets",
    response_model=list[AssetProductRead],
)
def list_assets(
    package_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[AssetProduct]:
    package = _package_for_user(db, package_id, user)
    return list(db.scalars(select(AssetProduct).where(AssetProduct.package_id == package.id).order_by(AssetProduct.asset_id)).all())


@router.get(
    "/organizations/{organization_id}/assets",
    response_model=list[AssetProductRead],
)
def list_organization_assets(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[AssetProduct]:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return list(
        db.scalars(
            select(AssetProduct)
            .join(ProcurementPackage, AssetProduct.package_id == ProcurementPackage.id)
            .join(Project, ProcurementPackage.project_id == Project.id)
            .where(Project.organization_id == organization_id)
            .order_by(AssetProduct.asset_id)
        ).all()
    )
