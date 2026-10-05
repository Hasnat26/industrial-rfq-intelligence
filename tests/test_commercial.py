from __future__ import annotations

from fastapi.testclient import TestClient

from freellmpool.api import app
from freellmpool.api.db import Base, engine

client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "commercial@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "commercial@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def test_subscription_defaults_to_starter_and_usage_is_aggregated() -> None:
    organization = client.post("/organizations", json={"name": "Commercial Org"}).json()

    plans = client.get("/commercial/plans")
    assert plans.status_code == 200
    assert {plan["key"] for plan in plans.json()} == {"STARTER", "PRO", "ENTERPRISE"}

    subscription = client.get(f"/organizations/{organization['id']}/subscription")
    assert subscription.status_code == 200
    assert subscription.json()["plan_key"] == "STARTER"

    first = client.post(
        f"/organizations/{organization['id']}/usage",
        json={"metric": "vendor_offers", "quantity": 3, "source_type": "offer"},
    )
    second = client.post(
        f"/organizations/{organization['id']}/usage",
        json={"metric": "vendor_offers", "quantity": 2, "source_type": "offer"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    summary = client.get(f"/organizations/{organization['id']}/usage")
    assert summary.status_code == 200
    assert summary.json()["usage"]["vendor_offers"] == 5
    assert summary.json()["limits"]["vendor_offers"] == 50


def test_usage_is_tenant_isolated() -> None:
    organization = client.post("/organizations", json={"name": "Commercial Tenant"}).json()
    other = client.post("/organizations", json={"name": "Other Tenant"}).json()
    response = client.get(f"/organizations/{other['id']}/usage")
    assert response.status_code == 404
    assert response.json()["detail"] == "organization not found"


def test_usage_limit_is_enforced() -> None:
    organization = client.post("/organizations", json={"name": "Limit Org"}).json()
    response = client.post(
        f"/organizations/{organization['id']}/usage",
        json={"metric": "vendor_offers", "quantity": 51},
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "vendor_offers plan limit exceeded"


def test_subscription_lifecycle_can_bind_provider_reference() -> None:
    organization = client.post("/organizations", json={"name": "Billing Org"}).json()
    response = client.put(
        f"/organizations/{organization['id']}/subscription",
        json={
            "plan_key": "PRO",
            "status": "ACTIVE",
            "billing_provider": "STRIPE",
            "external_customer_id": "cus_test_123",
            "external_subscription_id": "sub_test_123",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_key"] == "PRO"
    assert data["billing_provider"] == "STRIPE"
    assert data["external_customer_id"] == "cus_test_123"
    assert data["external_subscription_id"] == "sub_test_123"


def test_invalid_subscription_plan_is_rejected() -> None:
    organization = client.post("/organizations", json={"name": "Invalid Plan Org"}).json()
    response = client.put(
        f"/organizations/{organization['id']}/subscription",
        json={"plan_key": "UNKNOWN", "status": "ACTIVE"},
    )
    assert response.status_code == 422


def test_billing_webhook_requires_secret(monkeypatch) -> None:
    monkeypatch.delenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", raising=False)
    response = client.post(
        "/billing/webhooks/stripe",
        json={"id": "evt_missing_secret", "type": "customer.subscription.updated"},
    )
    assert response.status_code == 503


def test_billing_webhook_is_idempotent(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "test-secret")
    payload = {
        "id": "evt_123",
        "type": "customer.subscription.updated",
        "organization_id": 1,
    }
    headers = {"X-Billing-Webhook-Secret": "test-secret"}
    first = client.post("/billing/webhooks/stripe", json=payload, headers=headers)
    second = client.post("/billing/webhooks/stripe", json=payload, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["event_id"] == second.json()["event_id"]


def test_billing_webhook_rejects_invalid_secret(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "test-secret")
    response = client.post(
        "/billing/webhooks/stripe",
        json={"id": "evt_bad_secret", "type": "customer.subscription.updated"},
        headers={"X-Billing-Webhook-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_billing_webhook_receipts_are_tenant_visible(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "test-secret")
    organization = client.post("/organizations", json={"name": "Webhook Tenant"}).json()
    payload = {
        "id": "evt_visible",
        "type": "invoice.paid",
        "organization_id": organization["id"],
    }
    response = client.post(
        "/billing/webhooks/stripe",
        json=payload,
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 202
    listed = client.get(f"/organizations/{organization['id']}/billing/webhooks")
    assert listed.status_code == 200
    assert listed.json()[0]["external_event_id"] == "evt_visible"
    assert "payload" not in listed.json()[0]
