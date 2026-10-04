"""FastAPI application for the industrial procurement SaaS MVP."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from freellmpool.api.db import Organization, Project, ProcurementPackage, Requirement, VendorOffer, get_db, init_db
from freellmpool.api.schemas import (
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
)

app = FastAPI(title="Industrial RFQ Intelligence API", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "industrial-rfq-intelligence"}


@app.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)) -> Organization:
    organization = Organization(name=payload.name.strip())
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    if db.get(Organization, payload.organization_id) is None:
        raise HTTPException(status_code=404, detail="organization not found")
    project = Project(organization_id=payload.organization_id, name=payload.name.strip(), code=payload.code)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.post("/packages", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
def create_package(payload: PackageCreate, db: Session = Depends(get_db)) -> ProcurementPackage:
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


@app.post("/packages/{package_id}/offers", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
def add_offer(package_id: int, payload: OfferCreate, db: Session = Depends(get_db)) -> VendorOffer:
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


@app.post("/packages/{package_id}/technical-lock", response_model=PackageRead)
def lock_technical_bid(package_id: int, db: Session = Depends(get_db)) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    package.technical_bid_locked = True
    for offer in package.offers:
        if offer.technical_status == "PENDING":
            offer.technical_status = "ACCEPTED"
    db.commit()
    db.refresh(package)
    return package


@app.post("/packages/{package_id}/commercial-open", response_model=PackageRead)
def open_commercial_evaluation(package_id: int, db: Session = Depends(get_db)) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    if package.mode == "PROJECT_EPC" and not package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid must be locked before commercial evaluation")
    package.commercial_evaluation_open = True
    for offer in package.offers:
        offer.commercial_status = "OPEN"
    db.commit()
    db.refresh(package)
    return package


@app.get("/packages/{package_id}/comparison", response_model=ComparisonResponse)
def compare_package(package_id: int, db: Session = Depends(get_db)) -> ComparisonResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    rows: list[ComparisonRow] = []
    for requirement in package.requirements:
        for offer in package.offers:
            offered = None
            if requirement.parameter.casefold() in {"price", "commercial price"}:
                offered = offer.price
            status_value = "UNVERIFIED" if offered is None else "REVIEW_REQUIRED"
            rows.append(ComparisonRow(vendor=offer.vendor_name, parameter=requirement.parameter, required=requirement.required_value, offered=offered, status=status_value))
    return ComparisonResponse(
        package_id=package.id,
        technical_locked=package.technical_bid_locked,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )
