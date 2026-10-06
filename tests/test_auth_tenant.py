"""Authentication and server-side tenant-isolation tests.

Covers registration/login, unauthenticated rejection, and the full
cross-tenant matrix: reads, mutations, documents, and workflow actions
between Organization A and Organization B.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from freellmpool.api.app import app
from freellmpool.api.db import AuthSession, Base, SessionLocal, User, engine

client = TestClient(app)

PASSWORD = "correct-horse-battery"


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.headers.pop("Authorization", None)


def _account(email: str) -> dict[str, str]:
    """Register, log in, and return Authorization headers for the user."""
    registered = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert registered.status_code == 201, registered.text
    return _login(email)


def _login(email: str, password: str = PASSWORD) -> dict[str, str]:
    logged_in = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def _seed_tenant(email: str, org_name: str) -> dict:
    """Create a user with an org, project, package, offer, document, and issues."""
    headers = _account(email)
    organization = client.post(
        "/organizations", json={"name": org_name}, headers=headers
    )
    assert organization.status_code == 201, organization.text
    project = client.post(
        "/projects",
        json={"organization_id": organization.json()["id"], "name": f"{org_name} Project"},
        headers=headers,
    )
    assert project.status_code == 201, project.text
    package = client.post(
        "/packages",
        json={
            "project_id": project.json()["id"],
            "name": "Motor Package",
            "category": "MOTOR",
            "mode": "PROJECT_EPC",
            "requirements": [
                {"tag": "R-01", "parameter": "Rated voltage", "required_value": "415 V"}
            ],
        },
        headers=headers,
    )
    assert package.status_code == 201, package.text
    offer = client.post(
        f"/packages/{package.json()['id']}/offers",
        json={"vendor_name": "Vendor A", "price": "1000", "currency": "USD"},
        headers=headers,
    )
    assert offer.status_code == 201, offer.text
    document = client.post(
        f"/offers/{offer.json()['id']}/documents",
        files={"file": ("offer.txt", b"Rated voltage: 415 V", "text/plain")},
        headers=headers,
    )
    assert document.status_code == 201, document.text
    deviation = client.post(
        f"/offers/{offer.json()['id']}/deviations",
        json={
            "parameter": "Rated voltage",
            "severity": "MINOR",
            "description": "Vendor proposes 400 V design.",
        },
        headers=headers,
    )
    assert deviation.status_code == 201, deviation.text
    clarification = client.post(
        f"/offers/{offer.json()['id']}/clarifications",
        json={"question": "Confirm voltage basis.", "status": "ANSWERED", "response": "415 V"},
        headers=headers,
    )
    assert clarification.status_code == 201, clarification.text
    return {
        "headers": headers,
        "organization": organization.json(),
        "project": project.json(),
        "package": package.json(),
        "offer": offer.json(),
        "document": document.json(),
        "deviation": deviation.json(),
        "clarification": clarification.json(),
    }


def test_register_and_login_success() -> None:
    headers = _account("alice@example.com")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["organizations"] == []

    organization = client.post(
        "/organizations", json={"name": "Org A"}, headers=headers
    )
    assert organization.status_code == 201
    me = client.get("/auth/me", headers=headers).json()
    assert me["organizations"][0]["organization_id"] == organization.json()["id"]
    assert me["organizations"][0]["role"] == "OWNER"

    duplicate = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert duplicate.status_code == 409


def test_login_wrong_password_rejected() -> None:
    _account("bob@example.com")
    wrong = client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "not-the-password"},
    )
    assert wrong.status_code == 401
    assert "WWW-Authenticate" in wrong.headers


def test_login_unknown_user_rejected() -> None:
    unknown = client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "whatever-pass"},
    )
    assert unknown.status_code == 401


def test_password_and_token_never_stored_in_plaintext() -> None:
    _account("carol@example.com")
    headers = _login("carol@example.com")
    token = headers["Authorization"].removeprefix("Bearer ")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "carol@example.com"))
        assert user is not None
        assert PASSWORD not in user.password_hash
        assert user.password_hash.startswith("pbkdf2_sha256$")
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert session is not None
        assert session.token_hash != token
        assert token not in session.token_hash


def test_unauthenticated_requests_rejected() -> None:
    seeded = _seed_tenant("dave@example.com", "Org D")
    package_id = seeded["package"]["id"]
    offer_id = seeded["offer"]["id"]
    protected = [
        ("GET", f"/packages/{package_id}/rfq"),
        ("GET", f"/packages/{package_id}/offers"),
        ("GET", f"/packages/{package_id}/comparison"),
        ("GET", f"/packages/{package_id}/evidence"),
        ("GET", f"/documents/{seeded['document']['id']}"),
        ("GET", "/auth/me"),
        ("POST", "/organizations"),
        ("POST", "/projects"),
        ("POST", "/packages"),
        ("POST", f"/packages/{package_id}/offers"),
        ("POST", f"/offers/{offer_id}/claims"),
        ("POST", f"/offers/{offer_id}/technical-status"),
        ("POST", f"/offers/{offer_id}/revisions"),
        ("POST", f"/offers/{offer_id}/deviations"),
        ("POST", f"/offers/{offer_id}/clarifications"),
        ("POST", f"/offers/{offer_id}/documents"),
        ("POST", f"/packages/{package_id}/technical-lock"),
        ("POST", f"/packages/{package_id}/commercial-open"),
        ("POST", f"/deviations/{seeded['deviation']['id']}/resolve"),
        ("POST", f"/clarifications/{seeded['clarification']['id']}/close"),
    ]
    for method, path in protected:
        response = client.request(method, path, json={})
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
        assert "WWW-Authenticate" in response.headers, path

    assert client.get("/health").status_code == 200
    assert client.get(f"/packages/{package_id}/rfq").headers.get(
        "WWW-Authenticate"
    ) is not None


def test_invalid_bearer_token_rejected() -> None:
    forged = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/auth/me", headers=forged).status_code == 401
    malformed = {"Authorization": "Bearer "}
    assert client.get("/auth/me", headers=malformed).status_code == 401


def test_same_tenant_access_succeeds() -> None:
    seeded = _seed_tenant("erin@example.com", "Org E")
    headers = seeded["headers"]
    package_id = seeded["package"]["id"]
    offer_id = seeded["offer"]["id"]

    assert client.get(f"/packages/{package_id}/rfq", headers=headers).status_code == 200
    offers = client.get(f"/packages/{package_id}/offers", headers=headers)
    assert offers.status_code == 200
    assert len(offers.json()) == 1
    assert (
        client.get(f"/packages/{package_id}/comparison", headers=headers).status_code
        == 200
    )
    assert (
        client.get(f"/packages/{package_id}/evidence", headers=headers).status_code == 200
    )
    assert (
        client.get(f"/documents/{seeded['document']['id']}", headers=headers).status_code
        == 200
    )

    status_update = client.post(
        f"/offers/{offer_id}/technical-status",
        json={"status": "ACCEPTED"},
        headers=headers,
    )
    assert status_update.status_code == 200
    resolved = client.post(
        f"/deviations/{seeded['deviation']['id']}/resolve",
        json={"note": "Engineering accepted the deviation."},
        headers=headers,
    )
    assert resolved.status_code == 200
    closed = client.post(
        f"/clarifications/{seeded['clarification']['id']}/close",
        json={"note": "Answer accepted."},
        headers=headers,
    )
    assert closed.status_code == 200
    assert client.post(
        f"/packages/{package_id}/technical-lock", headers=headers
    ).status_code == 200
    assert client.post(
        f"/packages/{package_id}/commercial-open", headers=headers
    ).status_code == 200


def test_cross_tenant_reads_blocked() -> None:
    tenant_a = _seed_tenant("alice@example.com", "Org Alpha")
    tenant_b = _seed_tenant("bob@example.com", "Org Beta")
    attacker = tenant_b["headers"]
    package_id = tenant_a["package"]["id"]
    document_id = tenant_a["document"]["id"]

    reads = [
        f"/packages/{package_id}/rfq",
        f"/packages/{package_id}/offers",
        f"/packages/{package_id}/comparison",
        f"/packages/{package_id}/evidence",
        f"/documents/{document_id}",
    ]
    for path in reads:
        response = client.get(path, headers=attacker)
        assert response.status_code == 404, f"{path} -> {response.status_code}"

    # Cross-tenant responses are indistinguishable from nonexistent resources.
    missing = client.get("/packages/999999/rfq", headers=attacker)
    forbidden = client.get(f"/packages/{package_id}/rfq", headers=attacker)
    assert missing.status_code == forbidden.status_code == 404
    assert missing.json()["detail"] == forbidden.json()["detail"]


def test_cross_tenant_mutations_blocked() -> None:
    tenant_a = _seed_tenant("alice@example.com", "Org Alpha")
    tenant_b = _seed_tenant("bob@example.com", "Org Beta")
    attacker = tenant_b["headers"]
    package_id = tenant_a["package"]["id"]
    offer_id = tenant_a["offer"]["id"]
    deviation_id = tenant_a["deviation"]["id"]
    clarification_id = tenant_a["clarification"]["id"]

    mutations = [
        (
            "POST",
            f"/packages/{package_id}/offers",
            {"vendor_name": "Intruder"},
        ),
        ("POST", f"/offers/{offer_id}/revisions", {"technical_revision": "R9"}),
        (
            "POST",
            f"/offers/{offer_id}/claims",
            {"parameter": "Rated voltage", "value": "415 V"},
        ),
        (
            "POST",
            f"/offers/{offer_id}/technical-status",
            {"status": "REJECTED"},
        ),
        (
            "POST",
            f"/offers/{offer_id}/deviations",
            {"parameter": "Torque", "severity": "MINOR", "description": "Injected."},
        ),
        (
            "POST",
            f"/offers/{offer_id}/clarifications",
            {"question": "Injected question?"},
        ),
        ("POST", f"/deviations/{deviation_id}/resolve", {"note": "Injected resolution."}),
        ("POST", f"/clarifications/{clarification_id}/close", {"note": "Injected closure."}),
        ("POST", f"/packages/{package_id}/technical-lock", {}),
        ("POST", f"/packages/{package_id}/commercial-open", {}),
    ]
    for method, path, payload in mutations:
        response = client.request(method, path, json=payload, headers=attacker)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"

    upload = client.post(
        f"/offers/{offer_id}/documents",
        files={"file": ("intruder.txt", b"tampered", "text/plain")},
        headers=attacker,
    )
    assert upload.status_code == 404

    # The victim's data is untouched.
    victim = tenant_a["headers"]
    assert (
        client.get(f"/documents/{tenant_a['document']['id']}", headers=victim).status_code
        == 200
    )
    package = client.get(f"/packages/{package_id}/offers", headers=victim)
    assert package.status_code == 200
    assert len(package.json()) == 1


def test_failed_login_attempts_are_rate_limited_per_account(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES", "3")
    _account("brute@example.com")

    for _ in range(3):
        failed = client.post(
            "/auth/login",
            json={"email": "brute@example.com", "password": "wrong-pass"},
        )
        assert failed.status_code == 401

    # Once the failure budget is exhausted, even the correct password is refused.
    blocked = client.post(
        "/auth/login",
        json={"email": "brute@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_is_keyed_per_account_not_globally(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES", "2")
    _account("blocked@example.com")
    for _ in range(2):
        client.post(
            "/auth/login",
            json={"email": "blocked@example.com", "password": "wrong-pass"},
        )

    blocked = client.post(
        "/auth/login",
        json={"email": "blocked@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429

    # A different account on the same client is unaffected.
    _account("healthy@example.com")
    healthy = client.post(
        "/auth/login",
        json={"email": "healthy@example.com", "password": PASSWORD},
    )
    assert healthy.status_code == 200


def test_successful_login_resets_the_failure_counter(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES", "3")
    _account("reset@example.com")
    for _ in range(2):
        client.post(
            "/auth/login",
            json={"email": "reset@example.com", "password": "wrong-pass"},
        )
    ok = client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": PASSWORD},
    )
    assert ok.status_code == 200

    # The budget starts fresh after a successful authentication.
    for _ in range(2):
        again = client.post(
            "/auth/login",
            json={"email": "reset@example.com", "password": "wrong-pass"},
        )
        assert again.status_code == 401


def test_ip_failure_budget_blocks_password_spraying(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_LOGIN_IP_MAX_FAILURES", "3")
    _account("spray-valid@example.com")

    # Spray many distinct addresses from one source.
    for index in range(3):
        sprayed = client.post(
            "/auth/login",
            json={"email": f"spray-{index}@example.com", "password": "wrong-pass"},
        )
        assert sprayed.status_code == 401

    # Same source, valid credentials: further attempts are refused outright.
    refused = client.post(
        "/auth/login",
        json={"email": "spray-valid@example.com", "password": PASSWORD},
    )
    assert refused.status_code == 429


def test_login_block_expires_with_the_window(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES", "2")
    monkeypatch.setenv("INDUSTRIAL_RFQ_RATE_LIMIT_WINDOW_SECONDS", "0")
    _account("window@example.com")
    for _ in range(3):
        attempt = client.post(
            "/auth/login",
            json={"email": "window@example.com", "password": "wrong-pass"},
        )
        assert attempt.status_code == 401


def test_successful_login_purges_expired_sessions() -> None:
    headers = _account("purge@example.com")
    assert headers
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "purge@example.com"))
        assert user is not None
        user_id = user.id
        db.add(
            AuthSession(
                user_id=user_id,
                token_hash="expired-token-digest",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        db.commit()

    login = client.post(
        "/auth/login",
        json={"email": "purge@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200

    with SessionLocal() as db:
        remaining = list(
            db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)).all()
        )
    assert all(row.token_hash != "expired-token-digest" for row in remaining)
    assert len(remaining) == 2  # the two live sessions; the expired row is purged


def test_client_supplied_organization_id_cannot_switch_tenant() -> None:
    tenant_a = _seed_tenant("alice@example.com", "Org Alpha")
    tenant_b = _seed_tenant("bob@example.com", "Org Beta")

    # Organization B's user points their project payload at organization A.
    project = client.post(
        "/projects",
        json={"organization_id": tenant_a["organization"]["id"], "name": "Trojan Project"},
        headers=tenant_b["headers"],
    )
    assert project.status_code == 404

    package = client.post(
        "/packages",
        json={
            "project_id": tenant_a["project"]["id"],
            "name": "Trojan Package",
            "category": "MOTOR",
            "mode": "STANDARD",
        },
        headers=tenant_b["headers"],
    )
    assert package.status_code == 404

    # The attacker's own resources stay in their own organization.
    own_project = client.post(
        "/projects",
        json={"organization_id": tenant_b["organization"]["id"], "name": "Beta Project 2"},
        headers=tenant_b["headers"],
    )
    assert own_project.status_code == 201

    # Organization A's data still belongs to A only.
    alpha_projects = client.get(
        f"/packages/{tenant_a['package']['id']}/rfq", headers=tenant_b["headers"]
    )
    assert alpha_projects.status_code == 404
