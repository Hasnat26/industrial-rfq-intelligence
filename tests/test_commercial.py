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
