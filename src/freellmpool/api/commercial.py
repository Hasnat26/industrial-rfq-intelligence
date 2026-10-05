"""Commercial entitlement and usage metering foundations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import OrganizationSubscription, UsageRecord, User, get_db
from freellmpool.api.schemas import (
    OrganizationSubscriptionRead,
    SubscriptionPlanRead,
    UsageRecordCreate,
    UsageRecordRead,
    UsageSummaryResponse,
)

router = APIRouter(tags=["commercial"])

PLANS = {
    "STARTER": {
        "name": "Starter",
        "monthly_price_usd": 0.0,
        "limits": {"procurement_packages": 10, "vendor_offers": 50, "documents": 100},
    },
    "PRO": {
        "name": "Professional",
        "monthly_price_usd": 199.0,
        "limits": {"procurement_packages": 100, "vendor_offers": 1000, "documents": 2000},
    },
    "ENTERPRISE": {
        "name": "Enterprise",
        "monthly_price_usd": 0.0,
        "limits": {"procurement_packages": -1, "vendor_offers": -1, "documents": -1},
    },
}



def _usage_total(db: Session, organization_id: int, metric: str, subscription: OrganizationSubscription) -> float:
    rows = db.scalars(
        select(UsageRecord).where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.metric == metric,
            UsageRecord.recorded_at >= subscription.current_period_start,
            UsageRecord.recorded_at < subscription.current_period_end,
        )
    ).all()
    return sum(row.quantity for row in rows)


def enforce_limit(db: Session, organization_id: int, metric: str, quantity: float = 1.0) -> None:
    subscription = _subscription(db, organization_id)
    if subscription.status != "ACTIVE":
        raise HTTPException(status_code=402, detail="subscription is not active")
    limit = PLANS[subscription.plan_key]["limits"].get(metric)
    if limit is None or limit < 0:
        return
    if _usage_total(db, organization_id, metric, subscription) + quantity > limit:
        raise HTTPException(status_code=429, detail=f"{metric} plan limit exceeded")


def _member(db: Session, user: User, organization_id: int) -> None:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")


def _subscription(db: Session, organization_id: int) -> OrganizationSubscription:
    subscription = db.scalar(
        select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == organization_id
        )
    )
    if subscription is not None:
        return subscription
    now = datetime.now(UTC)
    subscription = OrganizationSubscription(
        organization_id=organization_id,
        plan_key="STARTER",
        status="ACTIVE",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


@router.get("/commercial/plans", response_model=list[SubscriptionPlanRead])
def list_plans() -> list[SubscriptionPlanRead]:
    return [SubscriptionPlanRead(key=key, **value) for key, value in PLANS.items()]


@router.get(
    "/organizations/{organization_id}/subscription",
    response_model=OrganizationSubscriptionRead,
)
def get_subscription(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> OrganizationSubscription:
    _member(db, user, organization_id)
    return _subscription(db, organization_id)


@router.post(
    "/organizations/{organization_id}/usage",
    response_model=UsageRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def record_usage(
    organization_id: int,
    payload: UsageRecordCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> UsageRecord:
    _member(db, user, organization_id)
    enforce_limit(db, organization_id, payload.metric, payload.quantity)
    db.add(UsageRecord(organization_id=organization_id, **payload.model_dump()))
    db.commit()
    record = db.scalar(select(UsageRecord).where(UsageRecord.organization_id == organization_id).order_by(UsageRecord.id.desc()))
    return record


@router.get(
    "/organizations/{organization_id}/usage",
    response_model=UsageSummaryResponse,
)
def usage_summary(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> UsageSummaryResponse:
    _member(db, user, organization_id)
    subscription = _subscription(db, organization_id)
    rows = list(
        db.scalars(
            select(UsageRecord).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.recorded_at >= subscription.current_period_start,
                UsageRecord.recorded_at < subscription.current_period_end,
            )
        ).all()
    )
    usage: dict[str, float] = {}
    for row in rows:
        usage[row.metric] = usage.get(row.metric, 0.0) + row.quantity
    return UsageSummaryResponse(
        organization_id=organization_id,
        plan_key=subscription.plan_key,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        usage=usage,
        limits=PLANS[subscription.plan_key]["limits"],
    )
