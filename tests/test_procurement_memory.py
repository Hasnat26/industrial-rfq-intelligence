from __future__ import annotations

import os

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
        json={"email": "memory@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "memory@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _seed_memory() -> tuple[dict, dict, dict]:
    organization = client.post(
        "/organizations",
        json={"name": f"Memory Org {os.urandom(4).hex()}"},
    ).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Paper Mill Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "415 V Motor Package",
            "category": "MOTOR",
            "mode": "PROJECT_EPC",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                }
            ],
        },
    ).json()
    offer = client.post(
        f"/packages/{package['id']}/offers",
        json={
            "vendor_name": "Vendor Memory",
            "manufacturer": "ABB",
            "model": "M3BP 160",
            "part_number": "3GBA162410",
            "price": "12500",
            "currency": "USD",
            "lead_time": "10 weeks",
            "warranty": "24 months",
        },
    ).json()
    claim = client.post(
        f"/offers/{offer['id']}/claims",
        json={
            "parameter": "Rated voltage",
            "value": "415 V",
            "evidence": "Quotation page 3",
            "claim_status": "VERIFIED",
        },
    )
    assert claim.status_code == 201
    assert client.post(
        f"/offers/{offer['id']}/technical-status",
        json={"status": "ACCEPTED"},
    ).status_code == 200
    assert client.post(f"/packages/{package['id']}/technical-lock").status_code == 200
    assert client.post(f"/packages/{package['id']}/commercial-open").status_code == 200
    assert client.post(
        f"/offers/{offer['id']}/commercial-status",
        json={"status": "IN_REVIEW"},
    ).status_code == 200
    assert client.post(
        f"/offers/{offer['id']}/commercial-status",
        json={"status": "COMPLETED"},
    ).status_code == 200
    decision = client.post(
        f"/packages/{package['id']}/decision",
        json={
            "selected_offer_id": offer["id"],
            "rationale": "Best technical fit and acceptable commercial terms.",
        },
    )
    assert decision.status_code == 201
    return organization, project, package


def test_procurement_memory_retrieves_vendor_product_decision_commercial_and_evidence_history() -> None:
    organization, _project, package = _seed_memory()
    response = client.get(
        f"/organizations/{organization['id']}/procurement-memory",
        params={"query": "Vendor Memory"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    entry = payload["entries"][0]
    assert entry["package_id"] == package["id"]
    assert entry["category"] == "MOTOR"
    assert entry["vendor_name"] == "Vendor Memory"
    assert entry["manufacturer"] == "ABB"
    assert entry["model"] == "M3BP 160"
    assert entry["part_number"] == "3GBA162410"
    assert entry["price"] == "12500"
    assert entry["lead_time"] == "10 weeks"
    assert entry["warranty"] == "24 months"
    assert entry["selected_for_purchase"] is True
    assert entry["decision_rationale"].startswith("Best technical fit")
    assert entry["evidence"][0]["parameter"] == "Rated voltage"
    assert entry["evidence"][0]["claim_status"] == "VERIFIED"


def test_procurement_memory_supports_vendor_category_and_package_filters() -> None:
    organization, _project, package = _seed_memory()
    vendor = client.get(
        f"/organizations/{organization['id']}/procurement-memory",
        params={"vendor": "memory"},
    )
    assert vendor.status_code == 200
    assert vendor.json()["total"] == 1
    category = client.get(
        f"/organizations/{organization['id']}/procurement-memory",
        params={"category": "MOTOR"},
    )
    assert category.status_code == 200
    assert category.json()["total"] == 1
    package_memory = client.get(f"/packages/{package['id']}/memory")
    assert package_memory.status_code == 200
    assert package_memory.json()["total"] == 1


def test_procurement_memory_is_tenant_isolated() -> None:
    organization, _project, package = _seed_memory()
    outsider = client.post(
        "/auth/register",
        json={"email": "memory-outsider@example.com", "password": "correct-horse-battery"},
    )
    assert outsider.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "memory-outsider@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    response = client.get(
        f"/organizations/{organization['id']}/procurement-memory",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 404
    package_response = client.get(
        f"/packages/{package['id']}/memory",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert package_response.status_code == 404


def test_product_memory_aggregates_explicit_identity_and_commercial_history() -> None:
    organization, _project, _package = _seed_memory()
    response = client.get(f"/organizations/{organization['id']}/procurement-memory/products")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_products"] == 1
    product = payload["products"][0]
    assert product["manufacturer"] == "ABB"
    assert product["model"] == "M3BP 160"
    assert product["part_number"] == "3GBA162410"
    assert product["offer_count"] == 1
    assert product["vendor_count"] == 1
    assert product["selected_count"] == 1
    assert product["observed_prices"] == ["12500"]
    assert product["observed_currencies"] == ["USD"]
    assert product["observed_lead_times"] == ["10 weeks"]
    assert product["observed_warranties"] == ["24 months"]
