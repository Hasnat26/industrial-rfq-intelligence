"""FastAPI application for the industrial procurement SaaS MVP."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from freellmpool.api.db import (
    Organization,
    ProcurementPackage,
    Project,
    Requirement,
    TechnicalClarification,
    TechnicalDeviation,
    VendorClaim,
    VendorDocument,
    VendorDocumentPage,
    VendorOffer,
    get_db,
    init_db,
)
from freellmpool.api.schemas import (
    ClaimCreate,
    ClaimRead,
    ComparisonResponse,
    ComparisonRow,
    EvidenceResponse,
    EvidenceRow,
    IssueResolution,
    OfferCreate,
    OfferRead,
    OfferRevisionCreate,
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
    VendorDocumentRead,
)
from freellmpool.industrial import (
    ClaimStatus,
    DocumentPage,
    EvidenceProvenance,
    VendorValue,
    build_evidence_register,
    build_matrix,
    document_text,
    extract_document_pages,
)
from freellmpool.industrial import Requirement as EngineRequirement

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_CHUNK_BYTES = 1024 * 1024
SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".pdf", ".txt", ".md"})
CLAIM_STATUSES: dict[str, ClaimStatus] = {
    "VERIFIED": "VERIFIED",
    "PARTIALLY VERIFIED": "PARTIALLY VERIFIED",
    "UNVERIFIED": "UNVERIFIED",
    "INFERENCE": "INFERENCE",
    "ASSUMPTION": "ASSUMPTION",
    "CONTRADICTED": "CONTRADICTED",
}


def _claim_status(value: str) -> ClaimStatus:
    """Map a persisted claim status onto the engine's literal claim states."""
    return CLAIM_STATUSES.get(value, "UNVERIFIED")


def _require_technical_stage_open(package: ProcurementPackage) -> None:
    """Reject writes that would mutate a frozen technical evaluation stage."""
    if package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    if package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is already open")


def _safe_filename(raw: str | None) -> str:
    """Reduce an uploaded filename to a safe basename without path components."""
    name = Path((raw or "").replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        raise HTTPException(status_code=422, detail="a valid filename is required")
    if len(name) > 255:
        raise HTTPException(status_code=422, detail="filename must be at most 255 characters")
    return name


def _extract_upload_pages(path: Path, filename: str) -> list[DocumentPage]:
    """Extract untrusted upload bytes, failing closed without leaking internals."""
    try:
        extracted = extract_document_pages(path)
    except ValueError as exc:
        if "unsupported document type" in str(exc):
            raise HTTPException(
                status_code=415,
                detail="unsupported document type; expected .pdf, .txt, or .md",
            ) from exc
        raise HTTPException(status_code=422, detail="document could not be parsed") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="document could not be parsed") from exc
    return [DocumentPage(filename, item.page, item.text) for item in extracted]


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
    _require_technical_stage_open(package)
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


@app.get("/packages/{package_id}/offers", response_model=list[OfferRead])
def list_package_offers(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> list[OfferRead]:
    """List the auditable offer/revision history for a package."""
    package = db.get(ProcurementPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="package not found")
    reveal_commercial = package.commercial_evaluation_open or package.mode != "PROJECT_EPC"
    return [
        OfferRead(
            id=offer.id,
            package_id=offer.package_id,
            vendor_name=offer.vendor_name,
            technical_revision=offer.technical_revision,
            technical_status=offer.technical_status,
            commercial_status=offer.commercial_status,
            price=offer.price if reveal_commercial else None,
            currency=offer.currency if reveal_commercial else None,
            lead_time=offer.lead_time if reveal_commercial else None,
            warranty=offer.warranty if reveal_commercial else None,
        )
        for offer in sorted(package.offers, key=lambda item: item.id)
    ]


@app.post(
    "/offers/{offer_id}/revisions",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_offer_revision(
    offer_id: int,
    payload: OfferRevisionCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    """Create the next technical revision without mutating earlier ones."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    revision = payload.technical_revision.strip()
    if not revision:
        raise HTTPException(status_code=422, detail="technical_revision must not be empty")
    for existing in offer.package.offers:
        if existing.vendor_name == offer.vendor_name and existing.technical_revision == revision:
            raise HTTPException(
                status_code=409,
                detail=f"revision {revision} already exists for {offer.vendor_name}",
            )
    revision_offer = VendorOffer(
        package_id=offer.package_id,
        vendor_name=offer.vendor_name,
        technical_revision=revision,
        source_text=payload.source_text,
    )
    db.add(revision_offer)
    db.commit()
    db.refresh(revision_offer)
    return revision_offer


@app.post("/offers/{offer_id}/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
def add_claim(
    offer_id: int, payload: ClaimCreate, db: Session = Depends(get_db)  # noqa: B008
) -> VendorClaim:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    claim_status = payload.claim_status.strip().upper()
    if claim_status not in CLAIM_STATUSES:
        raise HTTPException(status_code=422, detail="invalid claim status")
    has_location = any(
        value is not None
        for value in (
            payload.source_page,
            payload.source_section,
            payload.source_table,
            payload.source_cell,
        )
    )
    if payload.source_document_id is None and has_location:
        raise HTTPException(
            status_code=422,
            detail="provenance fields require source_document_id",
        )
    if payload.source_document_id is not None:
        document = db.get(VendorDocument, payload.source_document_id)
        if document is None or document.offer_id != offer_id:
            raise HTTPException(status_code=404, detail="source document not found for this offer")
    claim = VendorClaim(
        offer_id=offer_id,
        parameter=payload.parameter.strip(),
        value=payload.value.strip(),
        evidence=payload.evidence.strip(),
        claim_status=claim_status,
        source_document_id=payload.source_document_id,
        source_page=payload.source_page,
        source_section=payload.source_section,
        source_table=payload.source_table,
        source_cell=payload.source_cell,
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
    _require_technical_stage_open(offer.package)
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
    _require_technical_stage_open(offer.package)
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
    if deviation.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="deviation is already resolved")
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
    if clarification.status == "CLOSED":
        raise HTTPException(status_code=409, detail="clarification is already closed")
    if clarification.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    clarification.status = "CLOSED"
    clarification.resolution = payload.note.strip()
    db.commit()
    db.refresh(clarification)
    return clarification


@app.post(
    "/offers/{offer_id}/documents",
    response_model=VendorDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_offer_document(
    offer_id: int,
    file: UploadFile = File(...),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorDocument:
    """Ingest an untrusted vendor document as extracted, provenance-tagged text."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    filename = _safe_filename(file.filename)
    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail="unsupported document type; expected .pdf, .txt, or .md",
        )
    content_type = (file.content_type or "").strip()[:120] or None

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            total = 0
            while True:
                chunk = await file.read(DOCUMENT_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOCUMENT_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="document exceeds the maximum upload size of 10 MB",
                    )
                temporary.write(chunk)
        pages = _extract_upload_pages(temporary_path, filename)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    document = VendorDocument(
        offer_id=offer_id,
        filename=filename,
        content_type=content_type,
        document_type="VENDOR_OFFER",
        page_count=len(pages),
        extracted_text=document_text(pages),
    )
    document.pages = [
        VendorDocumentPage(page_number=page.page, text=page.text) for page in pages
    ]
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@app.get("/documents/{document_id}", response_model=VendorDocumentRead)
def read_document(
    document_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> VendorDocument:
    document = db.get(VendorDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@app.post("/offers/{offer_id}/technical-status", response_model=OfferRead)
def update_technical_status(
    offer_id: int,
    payload: TechnicalStatusUpdate,
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    offer = db.get(VendorOffer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
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
            _claim_status(claim.claim_status),
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


@app.get("/packages/{package_id}/evidence", response_model=EvidenceResponse)
def package_evidence(
    package_id: int, db: Session = Depends(get_db)  # noqa: B008
) -> EvidenceResponse:
    """Return the engine's evidence register with vendor/revision provenance."""
    package = db.get(ProcurementPackage, package_id)
    if package is None:
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
