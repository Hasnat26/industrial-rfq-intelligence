from __future__ import annotations

from fastapi.testclient import TestClient

from freellmpool.api.app import app
from freellmpool.api.db import Base, ProcurementPackage, SessionLocal, engine

client = TestClient(app)


def setup_function() -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in Base.metadata.tables.values():
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table.name}"')
        Base.metadata.create_all(bind=connection)
    client.headers.pop("Authorization", None)
    registered = client.post(
        "/auth/register",
        json={"email": "block1@example.com", "password": "correct-horse-battery"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "block1@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


def _package() -> int:
    organization = client.post("/organizations", json={"name": "Block 1 Org"}).json()
    project = client.post(
        "/projects",
        json={"organization_id": organization["id"], "name": "Block 1 Project"},
    ).json()
    package = client.post(
        "/packages",
        json={
            "project_id": project["id"],
            "name": "300 TPD Mill",
            "category": "PROCESS_PLANT",
            "requirements": [
                {
                    "tag": "R-01",
                    "parameter": "Rated voltage",
                    "required_value": "415 V",
                },
                {
                    "tag": "R-02",
                    "parameter": "Motor power",
                    "required_value": "75 kW",
                },
                {
                    "tag": "R-03",
                    "parameter": "Efficiency class",
                    "required_value": "IE3",
                },
                {
                    "tag": "R-04",
                    "parameter": "Ingress protection",
                    "required_value": "IP55",
                },
            ],
        },
    )
    assert package.status_code == 201, package.text
    return package.json()["id"]


def test_technical_evaluation_classifies_vendor_specific_gaps() -> None:
    package_id = _package()
    offer = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor A", "technical_revision": "R1"},
    )
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["id"]

    claims = [
        ("Rated voltage", "415 V", "VERIFIED"),
        ("Motor power", "75 kW", "VERIFIED"),
        ("Efficiency class", "IE2", "VERIFIED"),
        ("Ingress protection", "IP55", "UNVERIFIED"),
    ]
    for parameter, value, claim_status in claims:
        response = client.post(
            f"/offers/{offer_id}/claims",
            json={
                "parameter": parameter,
                "value": value,
                "evidence": f"Vendor A quotation: {parameter}",
                "claim_status": claim_status,
            },
        )
        assert response.status_code == 201, response.text

    evaluation = client.get(f"/packages/{package_id}/technical-evaluation")
    assert evaluation.status_code == 200, evaluation.text
    payload = evaluation.json()
    assert payload["rfq_revision"] == "R1"
    assert payload["rfq_revision_id"] > 0
    assert {row["offer_id"] for row in payload["rows"]} == {offer_id}
    assert all(row["rfq_revision_id"] == payload["rfq_revision_id"] for row in payload["rows"])
    assert payload["rows"][0]["status"] == "COMPLIANT"
    assert payload["rows"][0]["gap_type"] is None

    by_parameter = {row["parameter"]: row for row in payload["rows"]}
    assert by_parameter["Motor power"]["status"] == "COMPLIANT"
    assert by_parameter["Efficiency class"]["status"] == "DEVIATION"
    assert by_parameter["Efficiency class"]["gap_type"] == "DEVIATION"
    assert by_parameter["Ingress protection"]["status"] == "UNVERIFIED"
    assert by_parameter["Ingress protection"]["gap_type"] == "EVIDENCE_REQUIRED"


def test_missing_and_conflicting_claims_are_explicit_gaps() -> None:
    package_id = _package()
    offer = client.post(
        f"/packages/{package_id}/offers",
        json={"vendor_name": "Vendor B", "technical_revision": "R1"},
    )
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["id"]

    for value in ("415 V", "400 V"):
        response = client.post(
            f"/offers/{offer_id}/claims",
            json={
                "parameter": "Rated voltage",
                "value": value,
                "evidence": f"Vendor B quotation: {value}",
                "claim_status": "VERIFIED",
            },
        )
        assert response.status_code == 201, response.text

    evaluation = client.get(f"/packages/{package_id}/technical-evaluation")
    assert evaluation.status_code == 200, evaluation.text
    rows = {row["parameter"]: row for row in evaluation.json()["rows"]}
    assert rows["Rated voltage"]["status"] == "UNVERIFIED"
    assert rows["Rated voltage"]["gap_type"] == "CONFLICT"
    assert rows["Motor power"]["status"] == "UNVERIFIED"
    assert rows["Motor power"]["gap_type"] == "MISSING"

