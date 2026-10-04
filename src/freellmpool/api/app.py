"""FastAPI application for the industrial procurement SaaS MVP."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from freellmpool.api.db import (
    Organization,
    ProcurementPackage,
    Project,
    Requirement,
    TechnicalClarification,
    TechnicalDeviation,
    VendorClaim,
    VendorOffer,
    get_db,
    init_db,
)
from freellmpool.api.schemas import (
    ClaimCreate,
    ClaimRead,
    ComparisonResponse,
    ComparisonRow,
    OfferCreate,
    OfferRead,
    OrganizationCreate,
    OrganizationRead,
    PackageCreate,
    PackageRead,
    ProjectCreate,
    ProjectRead,
    RequirementCreate,
    RfqResponse,
    TechnicalClarificationCreate,
    TechnicalClarificationRead,
    TechnicalDeviationCreate,
    TechnicalDeviationRead,
    TechnicalStatusUpdate,
    IssueResolution,
)
from freellmpool.industrial import Requirement as EngineRequirement, VendorValue, build_matrix


def run() -> None:
    import uvicorn

    uvicorn.run(
        "freellmpool.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


app = FastAPI(title="Industrial RFQ Intelligence API", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "industrial-rfq-intelligence"}


@app.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate, db: Session = Depends(get_db)  # noqa: B008
) -> Organization:
    organization = Organization(name=payload.name.strip())
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db)  # noqa: B008
) -> Project:
    if db.get(Organization, payload.organization_id) is None:
        raise HTTPException(status_code=404, detail="organization not found")
    project = Project(
        organization_id=payload.organization_id,
        name=payload.name.strip(),
        code=payload.code,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.post("/packages", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: PackageCreate, db: Session = Depends(get_db)  # noqa: B008
) -> ProcurementPackage:
    if payload.mode not in {"STANDARD", "PROJECT_EPC"}:
        raise HTTPException(status_code=422, detail="mode must be STANDARD or PROJECT_EPC")
    if db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    package = ProcurementPackage(
        project_id=payload.project_id,
        name=payload.name.strip(),
        category=payload.category.strip(),
        mode=payload.mode,
    )
    for item in payload.requirements:
        package.requirements.append(
            Requirement(
                tag=item.tag.strip(),
                parameter=item.parameter.strip(),
                required_value=item.required_value.strip(),
                requirement_type=item.requirement_type,
                acceptance_rule=item.acceptance_rule,
            )
        )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


@app.get("/packages/{package_id}/rfq", response_model=RfqResponse)
def generate_rfq(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> RfqResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    requirements = [
        RequirementCreate(
            tag=item.tag,
            parameter=item.parameter,
            required_value=item.required_value,
            requirement_type=item.requirement_type,
            acceptance_rule=item.acceptance_rule,
        )
        for item in package.requirements
    ]
    instructions = [
        "Return a line-by-line technical offer against each requirement.",
        "State deviations and exclusions explicitly; do not leave them implicit.",
        "Submit the technical offer before commercial evaluation for PROJECT_EPC packages.",
        "Commercial data must identify currency, price basis, lead time, warranty and payment terms.",
        "Quote references and document/page evidence should be preserved where available.",
    ]
    return RfqResponse(
        package_id=package.id,
        title=f"RFQ - {package.name}",
        mode=package.mode,
        category=package.category,
        requirements=requirements,
        instructions=instructions,
    )


@app.post("/packages/{package_id}/offers", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
def add_offer(
    package_id: int, payload: OfferCreate, db: Session = Depends(get_db)  # noqa: B008
) -> VendorOffer:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    if package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is already open")
    offer = VendorOffer(
        package_id=package_id,
        vendor_name=payload.vendor_name.strip(),
        technical_revision=payload.technical_revision.strip(),
        price=payload.price,
        currency=payload.currency,
        lead_time=payload.lead_time,
        warranty=payload.warranty,
        source_text=payload.source_text,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


@app.post("/offers/{offer_id}/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
def add_claim(
    offer_id: int, payload: ClaimCreate, db: Session = Depends(get_db)  # noqa: B008
) -> VendorClaim:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.commercial_status == "OPEN":
        raise HTTPException(status_code=409, detail="technical claims are locked after commercial opening")
    claim = VendorClaim(
        offer_id=offer_id,
        parameter=payload.parameter.strip(),
        value=payload.value.strip(),
        evidence=payload.evidence.strip(),
        claim_status=payload.claim_status.strip().upper(),
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@app.post(
    "/offers/{offer_id}/deviations",
    response_model=TechnicalDeviationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_deviation(
    offer_id: int,
    payload: TechnicalDeviationCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalDeviation:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    severity = payload.severity.strip().upper()
    deviation_status = payload.status.strip().upper()
    if severity not in {"MINOR", "MAJOR"}:
        raise HTTPException(status_code=422, detail="severity must be MINOR or MAJOR")
    if deviation_status not in {"OPEN", "RESOLVED", "ACCEPTED", "REJECTED"}:
        raise HTTPException(status_code=422, detail="invalid deviation status")
    deviation = TechnicalDeviation(
        offer_id=offer_id,
        parameter=payload.parameter.strip(),
        severity=severity,
        description=payload.description.strip(),
        status=deviation_status,
        resolution=payload.resolution,
    )
    db.add(deviation)
    db.commit()
    db.refresh(deviation)
    return deviation


@app.post(
    "/offers/{offer_id}/clarifications",
    response_model=TechnicalClarificationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_clarification(
    offer_id: int,
    payload: TechnicalClarificationCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarification:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    clarification_status = payload.status.strip().upper()
    if clarification_status not in {"OPEN", "ANSWERED", "CLOSED"}:
        raise HTTPException(status_code=422, detail="invalid clarification status")
    clarification = TechnicalClarification(
        offer_id=offer_id,
        question=payload.question.strip(),
        response=payload.response,
        status=clarification_status,
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)
    return clarification


@app.post(
    "/deviations/{deviation_id}/resolve",
    response_model=TechnicalDeviationRead,
)
def resolve_deviation(
    deviation_id: int,
    payload: IssueResolution,
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalDeviation:
    deviation = db.get(TechnicalDeviation, deviation_id)
    if deviation is None:
        raise HTTPException(status_code=404, detail="deviation not found")
    if deviation.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    deviation.status = "RESOLVED"
    deviation.resolution = payload.note.strip()
    db.commit()
    db.refresh(deviation)
    return deviation


@app.post(
    "/clarifications/{clarification_id}/close",
    response_model=TechnicalClarificationRead,
)
def close_clarification(
    clarification_id: int,
    payload: IssueResolution,
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarification:
    clarification = db.get(TechnicalClarification, clarification_id)
    if clarification is None:
        raise HTTPException(status_code=404, detail="clarification not found")
    if clarification.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    clarification.status = "CLOSED"
    clarification.response = payload.note.strip()
    db.commit()
    db.refresh(clarification)
    return clarification


@app.post("/offers/{offer_id}/technical-status", response_model=OfferRead)
def update_technical_status(
    offer_id: int,
    payload: TechnicalStatusUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.package.commercial_evaluation_open:
        raise HTTPException(
            status_code=409,
            detail="technical status cannot change after commercial opening",
        )
    allowed = {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED", "ACCEPTED", "ACCEPTED_WITH_DEVIATION", "REJECTED"}
    status_value = payload.status.strip().upper()
    if status_value not in allowed:
        raise HTTPException(status_code=422, detail="invalid technical status")
    offer.technical_status = status_value
    db.commit()
    db.refresh(offer)
    return offer


@app.post("/packages/{package_id}/technical-lock", response_model=PackageRead)
def lock_technical_bid(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    if not package.offers:
        raise HTTPException(status_code=409, detail="at least one vendor offer is required")
    blocking_statuses = {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED"}
    blocking = [offer.vendor_name for offer in package.offers if offer.technical_status in blocking_statuses]
    unresolved = [
        f"{offer.vendor_name}: unresolved technical issue"
        for offer in package.offers
        if any(item.status == "OPEN" for item in offer.deviations)
        or any(item.status == "OPEN" for item in offer.clarifications)
    ]
    if unresolved:
        raise HTTPException(
            status_code=409,
            detail=f"technical issues remain unresolved: {', '.join(unresolved)}",
        )
    if blocking:
        raise HTTPException(
            status_code=409,
            detail=f"technical evaluation incomplete for: {', '.join(blocking)}",
        )
    package.technical_bid_locked = True
    db.commit()
    db.refresh(package)
    return package


@app.post("/packages/{package_id}/commercial-open", response_model=PackageRead)
def open_commercial_evaluation(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    if package.mode == "PROJECT_EPC" and not package.technical_bid_locked:
        raise HTTPException(
            status_code=409,
            detail="technical bid must be locked before commercial evaluation",
        )
    package.commercial_evaluation_open = True
    for offer in package.offers:
        if offer.technical_status in {"ACCEPTED", "ACCEPTED_WITH_DEVIATION"}:
            offer.commercial_status = "OPEN"
        else:
            offer.commercial_status = "LOCKED"
    db.commit()
    db.refresh(package)
    return package


@app.get("/packages/{package_id}/comparison", response_model=ComparisonResponse)
def compare_package(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> ComparisonResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
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
            claim.claim_status,
        )
        for offer in package.offers
        for claim in offer.claims
    ]
    matrix = build_matrix(requirements, vendor_values)
    rows = [
        ComparisonRow(
            vendor=row["vendor"],
            parameter=row["parameter"],
            required=row["required"],
            offered=None if row["offered"] == "MISSING" else row["offered"],
            status=row["status"],
        )
        for row in matrix
    ]
    return ComparisonResponse(
        package_id=package.id,
        technical_locked=package.technical_bid_locked,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )
