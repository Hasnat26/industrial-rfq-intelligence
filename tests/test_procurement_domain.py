from freellmpool.procurement_domain import (
    CommercialOfferRecord,
    CommercialStatus,
    ProcurementMode,
    ProcurementPackageRecord,
)


def test_project_epc_cannot_open_commercial_before_technical_lock() -> None:
    package = ProcurementPackageRecord(
        package_id="PKG-001",
        category="VFD",
        mode=ProcurementMode.PROJECT_EPC,
        commercial_offers=[
            CommercialOfferRecord(
                vendor_id="V-A",
                technical_offer_revision="R1",
                price="10000",
                currency="USD",
                lead_time="10 weeks",
                warranty="24 months",
                payment_terms="30% advance",
            )
        ],
    )

    try:
        package.open_commercial_evaluation()
    except ValueError as exc:
        assert "technical bid lock" in str(exc)
    else:
        raise AssertionError("commercial evaluation opened before technical lock")


def test_project_epc_opens_commercial_after_technical_lock() -> None:
    package = ProcurementPackageRecord(
        package_id="PKG-002",
        category="Motor",
        mode=ProcurementMode.PROJECT_EPC,
        commercial_offers=[
            CommercialOfferRecord(
                vendor_id="V-B",
                technical_offer_revision="R2",
                price="12000",
                currency="USD",
                lead_time="8 weeks",
                warranty="36 months",
                payment_terms="20% advance",
            )
        ],
    )

    package.lock_technical_bid()
    package.open_commercial_evaluation()

    assert package.technical_bid_locked is True
    assert package.commercial_offers[0].status == CommercialStatus.OPEN
