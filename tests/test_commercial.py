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


def test_billing_webhook_updates_subscription_state(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "test-secret")
    organization = client.post("/organizations", json={"name": "Billing State Org"}).json()
    subscription = client.get(f"/organizations/{organization['id']}/subscription")
    assert subscription.status_code == 200

    payload = {
        "id": "evt_subscription_past_due",
        "type": "subscription.past_due",
        "organization_id": organization["id"],
        "customer_id": "cus_456",
        "subscription_id": "sub_456",
        "current_period_start": "2026-10-01T00:00:00+00:00",
        "current_period_end": "2026-11-01T00:00:00+00:00",
    }
    response = client.post(
        "/billing/webhooks/stripe",
        json=payload,
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSED"

    updated = client.get(f"/organizations/{organization['id']}/subscription")
    assert updated.status_code == 200
    data = updated.json()
    assert data["status"] == "PAST_DUE"
    assert data["external_customer_id"] == "cus_456"
    assert data["external_subscription_id"] == "sub_456"


def test_unknown_billing_event_is_receipted_without_changing_status(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_BILLING_WEBHOOK_SECRET", "test-secret")
    organization = client.post("/organizations", json={"name": "Unknown Billing Event Org"}).json()
    response = client.post(
        "/billing/webhooks/stripe",
        json={
            "id": "evt_unknown",
            "type": "invoice.payment_succeeded",
            "organization_id": organization["id"],
        },
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "PROCESSED"
    subscription = client.get(f"/organizations/{organization['id']}/subscription").json()
    assert subscription["status"] == "ACTIVE"


def test_usage_reconciliation_reports_consistent_entitlements() -> None:
    organization = client.post("/organizations", json={"name": "Reconciliation Org"}).json()
    usage = client.post(
        f"/organizations/{organization['id']}/usage",
        json={"metric": "vendor_offers", "quantity": 5},
    )
    assert usage.status_code == 201
    response = client.get(f"/organizations/{organization['id']}/usage/reconciliation")
    assert response.status_code == 200
    data = response.json()
    assert data["subscription_status"] == "ACTIVE"
    assert data["plan_key"] == "STARTER"
    assert data["usage"]["vendor_offers"] == 5
    assert data["exceeded_metrics"] == []
    assert data["inactive"] is False
    assert data["period_expired"] is False


def test_usage_reconciliation_detects_existing_overage_without_mutating_state() -> None:
    organization = client.post("/organizations", json={"name": "Overage Reconciliation Org"}).json()
    response = client.put(
        f"/organizations/{organization['id']}/subscription",
        json={"plan_key": "PRO", "status": "ACTIVE"},
    )
    assert response.status_code == 200

    from freellmpool.api.db import SessionLocal, UsageRecord
    db = SessionLocal()
    try:
        db.add(
            UsageRecord(
                organization_id=organization["id"],
                metric="vendor_offers",
                quantity=1001,
            )
        )
        db.commit()
    finally:
        db.close()

    report = client.get(f"/organizations/{organization['id']}/usage/reconciliation")
    assert report.status_code == 200
    data = report.json()
    assert data["exceeded_metrics"] == ["vendor_offers"]
    subscription = client.get(f"/organizations/{organization['id']}/subscription").json()
    assert subscription["status"] == "ACTIVE"
    assert subscription["plan_key"] == "PRO"


def test_subscription_rollover_advances_expired_period(monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta
    from freellmpool.api.db import SessionLocal, OrganizationSubscription

    organization = client.post("/organizations", json={"name": "Rollover Org"}).json()
    db = SessionLocal()
    try:
        subscription = db.query(OrganizationSubscription).filter_by(
            organization_id=organization["id"]
        ).one()
        subscription.current_period_start = datetime(2026, 1, 1, tzinfo=UTC)
        subscription.current_period_end = datetime(2026, 1, 31, tzinfo=UTC)
        db.commit()
    finally:
        db.close()

    response = client.post(f"/organizations/{organization['id']}/subscription/rollover")
    assert response.status_code == 200
    data = response.json()
    assert data["rolled_over"] is True
    assert data["current_period_start"] > data["previous_period_start"]
    assert data["current_period_end"] > data["previous_period_end"]


def test_subscription_rollover_is_idempotent_when_period_current() -> None:
    organization = client.post("/organizations", json={"name": "Current Rollover Org"}).json()
    response = client.post(f"/organizations/{organization['id']}/subscription/rollover")
    assert response.status_code == 200
    data = response.json()
    assert data["rolled_over"] is False
    assert data["current_period_start"] == data["previous_period_start"]
    assert data["current_period_end"] == data["previous_period_end"]


def test_get_subscription_automatically_rolls_active_expired_period() -> None:
    from datetime import UTC, datetime
    from freellmpool.api.db import SessionLocal, OrganizationSubscription

    organization = client.post("/organizations", json={"name": "Automatic Rollover Org"}).json()
    db = SessionLocal()
    try:
        subscription = db.query(OrganizationSubscription).filter_by(
            organization_id=organization["id"]
        ).one()
        subscription.current_period_start = datetime(2026, 1, 1, tzinfo=UTC)
        subscription.current_period_end = datetime(2026, 1, 31, tzinfo=UTC)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/organizations/{organization['id']}/subscription")
    assert response.status_code == 200
    data = response.json()
    assert data["current_period_end"] > "2026-10-05T00:00:00+00:00"
    assert data["status"] == "ACTIVE"


def test_canceled_subscription_does_not_roll_forward() -> None:
    from datetime import UTC, datetime
    from freellmpool.api.db import SessionLocal, OrganizationSubscription

    organization = client.post("/organizations", json={"name": "Canceled Period Org"}).json()
    client.put(
        f"/organizations/{organization['id']}/subscription",
        json={"plan_key": "STARTER", "status": "CANCELED"},
    )
    db = SessionLocal()
    try:
        subscription = db.query(OrganizationSubscription).filter_by(
            organization_id=organization["id"]
        ).one()
        subscription.current_period_start = datetime(2026, 1, 1, tzinfo=UTC)
        subscription.current_period_end = datetime(2026, 1, 31, tzinfo=UTC)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/organizations/{organization['id']}/subscription")
    assert response.status_code == 200
    assert response.json()["current_period_end"].startswith("2026-01-31")


def test_internal_reconciliation_requires_secret(monkeypatch) -> None:
    monkeypatch.delenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET", raising=False)
    response = client.post("/commercial/internal/reconcile")
    assert response.status_code == 503


def test_internal_reconciliation_rolls_active_expired_subscriptions(monkeypatch) -> None:
    from datetime import UTC, datetime
    from freellmpool.api.db import SessionLocal, OrganizationSubscription

    monkeypatch.setenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET", "reconcile-secret")
    organization = client.post("/organizations", json={"name": "Internal Reconcile Org"}).json()
    db = SessionLocal()
    try:
        subscription = db.query(OrganizationSubscription).filter_by(
            organization_id=organization["id"]
        ).one()
        subscription.current_period_start = datetime(2026, 1, 1, tzinfo=UTC)
        subscription.current_period_end = datetime(2026, 1, 31, tzinfo=UTC)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/commercial/internal/reconcile",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    assert data["rolled_over"] == 1
    assert data["unchanged"] == 0


def test_usage_reconciliation_reports_unknown_and_negative_usage_anomalies() -> None:
    from freellmpool.api.db import SessionLocal, UsageRecord

    organization = client.post("/organizations", json={"name": "Anomaly Org"}).json()
    db = SessionLocal()
    try:
        db.add_all(
            [
                UsageRecord(
                    organization_id=organization["id"],
                    metric="unknown_metric",
                    quantity=3,
                ),
                UsageRecord(
                    organization_id=organization["id"],
                    metric="vendor_offers",
                    quantity=-2,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get(f"/organizations/{organization['id']}/usage/reconciliation")
    assert response.status_code == 200
    data = response.json()
    assert data["unknown_metrics"] == ["unknown_metric"]
    assert data["negative_usage_metrics"] == ["vendor_offers"]


def test_internal_reconciliation_creates_audit_run(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET", "reconcile-secret")
    organization = client.post("/organizations", json={"name": "Audit Run Org"}).json()
    response = client.post(
        "/commercial/internal/reconcile",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["processed"] == 1
    runs = client.get(
        "/commercial/internal/reconcile/runs",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert runs.status_code == 200
    run = runs.json()[0]
    assert run["status"] == "COMPLETED"
    assert run["processed"] == 1
    assert run["rolled_over"] == 0
    assert run["unchanged"] == 1
    assert run["completed_at"] is not None
    assert run["error"] is None


def test_reconciliation_health_reports_no_runs(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET", "reconcile-secret")
    response = client.get(
        "/commercial/internal/reconcile/health",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NO_RUNS"


def test_reconciliation_health_reports_latest_completed_run(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_RFQ_COMMERCIAL_RECONCILIATION_SECRET", "reconcile-secret")
    run = client.post(
        "/commercial/internal/reconcile",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert run.status_code == 200

    response = client.get(
        "/commercial/internal/reconcile/health",
        headers={"X-Commercial-Reconciliation-Secret": "reconcile-secret"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["last_run_status"] == "COMPLETED"
    assert data["last_run_completed_at"] is not None


def test_scheduler_safe_reconciliation_runner_records_completion() -> None:
    from freellmpool.api.db import SessionLocal, CommercialReconciliationRun
    from freellmpool.api.reconciliation import run_commercial_reconciliation

    client.post("/organizations", json={"name": "Scheduler Runner Org"})
    db = SessionLocal()
    try:
        result = run_commercial_reconciliation(db)
        assert result.processed == 1
        run = db.query(CommercialReconciliationRun).order_by(CommercialReconciliationRun.id.desc()).first()
        assert run is not None
        assert run.status == "COMPLETED"
        assert run.completed_at is not None
    finally:
        db.close()
