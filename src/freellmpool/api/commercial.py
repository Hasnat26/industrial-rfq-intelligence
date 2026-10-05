"""Commercial entitlement and usage metering foundations."""

from __future__ import annotations

import os

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
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
    SubscriptionLifecycleUpdate,
    UsageReconciliationResponse,
    SubscriptionRolloverResponse,
    CommercialReconciliationResponse,
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
        if subscription.status in {"ACTIVE", "TRIALING", "PAST_DUE"} and _rollover_if_expired(db, subscription, datetime.now(UTC)):
            db.commit()
            db.refresh(subscription)
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


@router.put(
    "/organizations/{organization_id}/subscription",
    response_model=OrganizationSubscriptionRead,
)
def update_subscription(
    organization_id: int,
    payload: SubscriptionLifecycleUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> OrganizationSubscription:
    _member(db, user, organization_id)
    if payload.plan_key not in PLANS:
        raise HTTPException(status_code=422, detail="unknown subscription plan")
    if payload.status not in {"ACTIVE", "PAST_DUE", "CANCELED", "TRIALING"}:
        raise HTTPException(status_code=422, detail="invalid subscription status")
    subscription = _subscription(db, organization_id)
    subscription.plan_key = payload.plan_key
    subscription.status = payload.status
    if subscription.status in {"ACTIVE", "TRIALING", "PAST_DUE"}:
        _rollover_if_expired(db, subscription, datetime.now(UTC))
    subscription.billing_provider = payload.billing_provider
    subscription.external_customer_id = payload.external_customer_id
    subscription.external_subscription_id = payload.external_subscription_id
    if payload.current_period_start is not None:
        subscription.current_period_start = payload.current_period_start
    if payload.current_period_end is not None:
        subscription.current_period_end = payload.current_period_end
    subscription.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(subscription)
    return subscription


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


@router.get(
    "/organizations/{organization_id}/usage/reconciliation",
    response_model=UsageReconciliationResponse,
)
def usage_reconciliation(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> UsageReconciliationResponse:
    _member(db, user, organization_id)
    subscription = _subscription(db, organization_id)
    now = datetime.now(UTC)
    rows = db.scalars(
        select(UsageRecord).where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.recorded_at >= subscription.current_period_start,
            UsageRecord.recorded_at < subscription.current_period_end,
        )
    ).all()
    usage: dict[str, float] = {}
    for row in rows:
        usage[row.metric] = usage.get(row.metric, 0.0) + row.quantity
    limits = PLANS[subscription.plan_key]["limits"]
    exceeded = [
        metric for metric, limit in limits.items()
        if limit >= 0 and usage.get(metric, 0.0) > limit
    ]
    unknown_metrics = sorted(set(usage) - set(limits))
    negative_usage_metrics = sorted(metric for metric, quantity in usage.items() if quantity < 0)
    return UsageReconciliationResponse(
        organization_id=organization_id,
        subscription_status=subscription.status,
        plan_key=subscription.plan_key,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        usage=usage,
        limits=limits,
        exceeded_metrics=exceeded,
        inactive=subscription.status != "ACTIVE",
        period_expired=subscription.current_period_end <= now,
        unknown_metrics=unknown_metrics,
        negative_usage_metrics=negative_usage_metrics,
    )


def _rollover_if_expired(db: Session, subscription: OrganizationSubscription, now: datetime) -> bool:
    if subscription.current_period_end > now:
        return False
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    duration = period_end - period_start
    if duration.total_seconds() <= 0:
        duration = timedelta(days=30)
    while subscription.current_period_end <= now:
        subscription.current_period_start = subscription.current_period_end
        subscription.current_period_end = subscription.current_period_end + duration
    subscription.updated_at = now
    return True


@router.post(
    "/organizations/{organization_id}/subscription/rollover",
    response_model=SubscriptionRolloverResponse,
)
def rollover_subscription(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> SubscriptionRolloverResponse:
    _member(db, user, organization_id)
    subscription = _subscription(db, organization_id)
    previous_start = subscription.current_period_start
    previous_end = subscription.current_period_end
    rolled_over = False
    if subscription.status in {"ACTIVE", "TRIALING", "PAST_DUE"}:
        rolled_over = _rollover_if_expired(db, subscription, datetime.now(UTC))
    if rolled_over:
        db.commit()
        db.refresh(subscription)
    return SubscriptionRolloverResponse(
        organization_id=organization_id,
        rolled_over=rolled_over,
        previous_period_start=previous_start,
        previous_period_end=previous_end,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        status=subscription.status,
        plan_key=subscription.plan_key,
    )


@router.post(
    "/commercial/internal/reconcile",
    response_model=CommercialReconciliationResponse,
)
def reconcile_commercial_state(
    x_commercial_reconciliation_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),  # noqa: B008
) -> CommercialReconciliationResponse:
    expected = os.getenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="commercial reconciliation secret is not configured")
    if x_commercial_reconciliation_secret != expected:
        raise HTTPException(status_code=401, detail="invalid commercial reconciliation secret")
    subscriptions = db.scalars(select(OrganizationSubscription)).all()
    processed = 0
    rolled_over = 0
    for subscription in subscriptions:
        processed += 1
        if subscription.status in {"ACTIVE", "TRIALING", "PAST_DUE"}:
            if _rollover_if_expired(db, subscription, datetime.now(UTC)):
                rolled_over += 1
    if rolled_over:
        db.commit()
    return CommercialReconciliationResponse(
        processed=processed,
        rolled_over=rolled_over,
        unchanged=processed - rolled_over,
    )
