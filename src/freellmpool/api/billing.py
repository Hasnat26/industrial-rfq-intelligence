"""Provider-neutral billing webhook receipt boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from freellmpool.api.auth import get_current_user, is_member
from freellmpool.api.db import (
    BillingWebhookEvent,
    OrganizationSubscription,
    SessionLocal,
    User,
    get_db,
)
from freellmpool.api.schemas import BillingWebhookEventRead

router = APIRouter(tags=["billing"])

_STATUS_MAP = {
    "subscription.active": "ACTIVE",
    "subscription.updated": "ACTIVE",
    "subscription.trialing": "TRIALING",
    "subscription.past_due": "PAST_DUE",
    "subscription.canceled": "CANCELED",
    "subscription.cancelled": "CANCELED",
}


def _subscription_from_event(db: Session, payload: dict[str, object], provider: str) -> OrganizationSubscription | None:
    organization_id = payload.get("organization_id")
    if organization_id is None:
        return None
    try:
        organization_id = int(organization_id)
    except (TypeError, ValueError):
        return None

    subscription = db.scalar(
        select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == normalized_organization_id
        )
    )
    if subscription is None:
        return None

    subscription.billing_provider = provider.upper()
    external_customer_id = payload.get("customer_id")
    external_subscription_id = payload.get("subscription_id")
    if external_customer_id is not None:
        subscription.external_customer_id = str(external_customer_id)
    if external_subscription_id is not None:
        subscription.external_subscription_id = str(external_subscription_id)

    mapped_status = _STATUS_MAP.get(str(payload.get("type", "")).strip().lower())
    if mapped_status:
        subscription.status = mapped_status

    period_start = payload.get("current_period_start")
    period_end = payload.get("current_period_end")
    for value, attribute in ((period_start, "current_period_start"), (period_end, "current_period_end")):
        if value is not None:
            try:
                setattr(subscription, attribute, datetime.fromisoformat(str(value)))
            except ValueError:
                pass
    subscription.updated_at = datetime.now(UTC)
    return subscription



def _webhook_secret() -> str:
    return os.getenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "")


@router.post("/billing/webhooks/{provider}", status_code=202)
async def receive_billing_webhook(
    provider: str,
    request: Request,
    x_billing_webhook_secret: str | None = Header(default=None),
) -> dict[str, object]:
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="billing webhook secret is not configured")
    if not x_billing_webhook_secret or not hmac.compare_digest(x_billing_webhook_secret, secret):
        raise HTTPException(status_code=401, detail="invalid billing webhook secret")

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid webhook JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="webhook payload must be an object")

    external_event_id = str(payload.get("id", "")).strip()
    event_type = str(payload.get("type", "")).strip()
    if not external_event_id or not event_type:
        raise HTTPException(status_code=400, detail="webhook id and type are required")

    payload_hash = hashlib.sha256(body).hexdigest()
    db = SessionLocal()
    try:
        existing = db.scalar(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.provider == provider,
                BillingWebhookEvent.external_event_id == external_event_id,
            )
        )
        if existing is not None:
            return {"status": existing.status, "event_id": existing.id, "duplicate": True}

        organization_id = payload.get("organization_id")
        if organization_id is not None:
            try:
                organization_id = int(organization_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="organization_id must be an integer") from exc

        event = BillingWebhookEvent(
            organization_id=organization_id,
            provider=provider.upper(),
            external_event_id=external_event_id,
            event_type=event_type,
            payload_hash=payload_hash,
            status="RECEIVED",
            received_at=datetime.now(UTC),
        )
        db.add(event)
        db.flush()
        _subscription_from_event(db, payload, provider)
        event.status = "PROCESSED"
        event.processed_at = datetime.now(UTC)
        db.commit()
        db.refresh(event)
        return {"status": event.status, "event_id": event.id, "duplicate": False}
    finally:
        db.close()


@router.get(
    "/organizations/{organization_id}/billing/webhooks",
    response_model=list[BillingWebhookEventRead],
)
def list_billing_webhooks(
    organization_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[BillingWebhookEvent]:
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    return list(
        db.scalars(
            select(BillingWebhookEvent)
            .where(BillingWebhookEvent.organization_id == organization_id)
            .order_by(BillingWebhookEvent.received_at.desc())
        ).all()
    )
