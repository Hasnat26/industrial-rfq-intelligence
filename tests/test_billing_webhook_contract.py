"""Billing webhook contract and identity-hardening regression tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from freellmpool.api.app import app
from freellmpool.api.db import (
    Base,
    Organization,
    OrganizationSubscription,
    SessionLocal,
    engine,
)
from freellmpool.api.billing import _normalize_provider

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    os.environ["INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET"] = "test-secret"


def teardown_function() -> None:
    os.environ.pop("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", None)


def _seed_subscription() -> int:
    with SessionLocal() as db:
        organization = Organization(name="Billing Test Org")
        db.add(organization)
        db.flush()
        db.add(
            OrganizationSubscription(
                organization_id=organization.id,
                plan_key="PRO",
                status="ACTIVE",
                current_period_start=datetime.now(UTC),
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )
        )
        db.commit()
        return organization.id


def _payload(organization_id: int, event_id: str = "evt_1") -> dict[str, object]:
    return {
        "id": event_id,
        "type": "subscription.active",
        "organization_id": organization_id,
        "customer_id": "cus_1",
        "subscription_id": "sub_1",
        "current_period_start": "2026-10-01T00:00:00+00:00",
        "current_period_end": "2026-11-01T00:00:00+00:00",
    }


def test_provider_normalization_and_validation() -> None:
    assert _normalize_provider(" stripe ") == "STRIPE"
    assert _normalize_provider("provider-1") == "PROVIDER-1"
    with pytest.raises(HTTPException) as exc:
        _normalize_provider("bad provider")
    assert exc.value.status_code == 400


def test_webhook_rejects_unsupported_event_before_persistence() -> None:
    organization_id = _seed_subscription()
    payload = _payload(organization_id)
    payload["type"] = "invoice.unknown"

    response = client.post(
        "/billing/webhooks/stripe",
        json=payload,
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported billing event type"


def test_webhook_requires_existing_subscription() -> None:
    response = client.post(
        "/billing/webhooks/stripe",
        json=_payload(999999),
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "subscription not found"


def test_webhook_binds_external_subscription_identity() -> None:
    organization_id = _seed_subscription()

    first = client.post(
        "/billing/webhooks/stripe",
        json=_payload(organization_id),
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert first.status_code == 202
    assert first.json()["duplicate"] is False

    conflicting = _payload(organization_id, event_id="evt_2")
    conflicting["subscription_id"] = "sub_attacker"
    response = client.post(
        "/billing/webhooks/stripe",
        json=conflicting,
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "billing subscription identity mismatch"


def test_webhook_accepts_supported_lifecycle_events() -> None:
    organization_id = _seed_subscription()

    for index, event_type in enumerate(
        ["subscription.trialing", "subscription.paused", "subscription.resumed", "subscription.expired"],
        start=1,
    ):
        payload = _payload(organization_id, event_id=f"evt_{index}")
        payload["type"] = event_type
        response = client.post(
            "/billing/webhooks/stripe",
            json=payload,
            headers={"X-Billing-Webhook-Secret": "test-secret"},
        )
        assert response.status_code == 202, response.text
