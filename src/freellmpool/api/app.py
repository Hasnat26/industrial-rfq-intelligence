    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    if not package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is not open")
    rows = [
        CommercialComparisonRow(
            offer_id=offer.id,
            vendor=offer.vendor_name,
            technical_revision=offer.technical_revision,
            technical_status=offer.technical_status,
            commercial_status=offer.commercial_status,
            price=offer.price,
            currency=offer.currency,
            lead_time=offer.lead_time,
            warranty=offer.warranty,
        )
        for offer in sorted(package.offers, key=lambda item: item.id)
        if offer.commercial_status != "LOCKED"
    ]
    return CommercialComparisonResponse(
        package_id=package.id,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )


@app.get("/packages/{package_id}/comparison", response_model=ComparisonResponse)
def compare_package(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ComparisonResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")

    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in package.requirements
    ]
    vendor_values = [
        VendorValue(
            offer.vendor_name,
            claim.parameter,
            claim.value,
            claim.evidence,
            _claim_status(claim.claim_status),
        )
        for offer in package.offers
        for claim in offer.claims
    ]
    matrix = build_matrix(
        requirements,
        vendor_values,
        vendors=[offer.vendor_name for offer in package.offers],
    )
    claim_parameters_by_vendor = {
        offer.vendor_name: {
            _claim.parameter.casefold().strip()
            for _claim in offer.claims
        }
        for offer in package.offers
    }
    rows = []
    for row in matrix:
        status = row["status"]
        if row["parameter"].casefold().strip() not in claim_parameters_by_vendor.get(
            row["vendor"], set()
        ):
            status = "UNVERIFIED"
        rows.append(
            ComparisonRow(
                vendor=row["vendor"],
                parameter=row["parameter"],
                required=row["required"],
                offered=None if row["offered"] == "MISSING" else row["offered"],
                status=status,
            )
        )
    return ComparisonResponse(
        package_id=package.id,
        technical_locked=package.technical_bid_locked,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )


@app.get("/packages/{package_id}/evidence", response_model=EvidenceResponse)
def package_evidence(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EvidenceResponse:
    """Return the engine's evidence register with vendor/revision provenance."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in package.requirements
    ]
    claims: list[tuple[VendorOffer, VendorClaim]] = []
    vendor_values: list[VendorValue] = []
    for offer in package.offers:
        for claim in offer.claims:
            claims.append((offer, claim))
            provenance = (
                EvidenceProvenance(
                    source=claim.source_document.filename,
                    page=claim.source_page,
                    section=claim.source_section,
                    table=claim.source_table,
                    cell=claim.source_cell,
                )
                if claim.source_document is not None
                else None
            )
            vendor_values.append(
                VendorValue(
                    offer.vendor_name,
                    claim.parameter,
                    claim.value,
                    claim.evidence,
                    _claim_status(claim.claim_status),
                    provenance,
                )
            )
    register = build_evidence_register(requirements, vendor_values)
    rows: list[EvidenceRow] = []
    for (offer, claim), entry in zip(claims, register, strict=True):
        document = claim.source_document
        rows.append(
            EvidenceRow(
                claim_id=claim.id,
                offer_id=offer.id,
                vendor=offer.vendor_name,
                technical_revision=offer.technical_revision,
                field=entry["field"],
                value=entry["value"],
                evidence=entry["evidence"],
                claim_status=entry["claim_status"],
                review_required=entry["review_required"],
                source=entry["source"],
                page=claim.source_page,
                section=entry["section"],
                table=entry["table"],
                cell=entry["cell"],
                source_document_id=claim.source_document_id,
                source_document_filename=document.filename if document is not None else None,
            )
        )
    return EvidenceResponse(package_id=package.id, rows=rows)


@app.get("/packages/{package_id}/report")
def package_report(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, object]:
    """Return the package as a machine-readable evidence-aware review report."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")

    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in package.requirements
    ]
    vendor_values: list[VendorValue] = []
    for offer in package.offers:
        for claim in offer.claims:
            provenance = (