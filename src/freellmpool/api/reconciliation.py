"""Operational reconciliation runner for scheduled deployments."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.db import CommercialReconciliationRun, OrganizationSubscription
from freellmpool.api.schemas import CommercialReconciliationResponse


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive timestamps and aware timestamps to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def rollover_if_expired(subscription: OrganizationSubscription, now: datetime) -> bool:
    now_utc = _as_utc(now)
    period_start = _as_utc(subscription.current_period_start)
    period_end = _as_utc(subscription.current_period_end)
    if period_end > now_utc:
        return False
    duration = period_end - period_start
    if duration.total_seconds() <= 0:
        duration = timedelta(days=30)
    while period_end <= now_utc:
        period_start = period_end
        period_end = period_end + duration
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.updated_at = now_utc
    return True


def run_commercial_reconciliation(db: Session) -> CommercialReconciliationResponse:
    run = CommercialReconciliationRun(status="RUNNING")
    db.add(run)
    db.flush()
    try:
        subscriptions = db.scalars(select(OrganizationSubscription)).all()
        processed = 0
        rolled_over = 0
        for subscription in subscriptions:
            processed += 1
            if subscription.status in {"ACTIVE", "TRIALING", "PAST_DUE"}:
                if rollover_if_expired(subscription, datetime.now(UTC)):
                    rolled_over += 1
        run.processed = processed
        run.rolled_over = rolled_over
        run.unchanged = processed - rolled_over
        run.status = "COMPLETED"
        run.completed_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        db.commit()
        return CommercialReconciliationResponse(
            processed=processed,
            rolled_over=rolled_over,
            unchanged=processed - rolled_over,
        )
    except Exception as exc:
        db.rollback()
        failed = CommercialReconciliationRun(status="FAILED", error=str(exc)[:2000])
        db.add(failed)
        db.commit()
        raise HTTPException(status_code=500, detail="commercial reconciliation failed") from exc


def scheduler_secret_configured() -> bool:
    return bool(os.getenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET"))
