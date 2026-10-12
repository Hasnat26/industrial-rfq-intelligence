"""Operational reconciliation runner for scheduled deployments."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.db import CommercialReconciliationRun, OrganizationSubscription
from freellmpool.api.schemas import CommercialReconciliationResponse


_logger = logging.getLogger(__name__)


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
    try:
        db.add(run)
        db.flush()
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
        original_error_type = type(exc).__name__
        rollback_error_type: str | None = None
        try:
            db.rollback()
        except Exception as rollback_exc:
            rollback_error_type = type(rollback_exc).__name__

        persistence_error_type: str | None = None
        cleanup_rollback_error_type: str | None = None
        try:
            failed = CommercialReconciliationRun(
                status="FAILED",
                error=f"reconciliation failed ({original_error_type})",
            )
            db.add(failed)
            db.commit()
        except Exception as persistence_exc:
            persistence_error_type = type(persistence_exc).__name__
            try:
                db.rollback()
            except Exception as cleanup_rollback_exc:
                cleanup_rollback_error_type = type(cleanup_rollback_exc).__name__

        if persistence_error_type is None:
            if rollback_error_type:
                _logger.error(
                    "commercial reconciliation failed (%s); rollback failed (%s); "
                    "failure record persistence succeeded",
                    original_error_type,
                    rollback_error_type,
                )
            else:
                _logger.error(
                    "commercial reconciliation failed (%s); failure record persisted",
                    original_error_type,
                )
        elif cleanup_rollback_error_type:
            _logger.error(
                "commercial reconciliation failed (%s); rollback failed (%s); "
                "failure-record persistence failed (%s); cleanup rollback failed (%s); "
                "failure record was not persisted",
                original_error_type,
                rollback_error_type or "none",
                persistence_error_type,
                cleanup_rollback_error_type,
            )
        else:
            _logger.error(
                "commercial reconciliation failed (%s); rollback failed (%s); "
                "failure-record persistence failed (%s); failure record was not persisted",
                original_error_type,
                rollback_error_type or "none",
                persistence_error_type,
            )

        raise HTTPException(
            status_code=500, detail="commercial reconciliation failed"
        ) from None


def scheduler_secret_configured() -> bool:
    return bool(
        os.getenv("INDUSTRIAL_RFQ_INTERNAL_RECONCILIATION_SECRET")
        or os.getenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET")
    )
