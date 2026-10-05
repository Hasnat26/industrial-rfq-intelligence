"""FastAPI application for the industrial procurement SaaS MVP."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freellmpool.api.auth import authenticate, get_current_user, is_member, issue_session
from freellmpool.api.db import (
    Organization,
    OrganizationMembership,
    OrganizationSubscription,
    ProcurementAuditEvent,
    ProcurementDecision,
    ProcurementPackage,
    Project,
    Requirement,
    TechnicalClarification,
    TechnicalDeviation,
    User,
    VendorClaim,
    VendorDocument,
    VendorDocumentPage,
    VendorOffer,
    get_db,
    init_db,
)
from freellmpool.api.schemas import (
    AuditEventRead,
    ClaimCreate,
    ClaimRead,
    CommercialComparisonResponse,
    CommercialComparisonRow,
    CommercialStatusUpdate,
    ComparisonResponse,
    ComparisonRow,
    CurrentUserRead,
    DecisionCreate,
    DecisionRead,
    EvidenceResponse,
    EvidenceRow,
    IssueResolution,
    LoginRequest,
    OfferCreate,
    OfferRead,
    OfferRevisionCreate,
    OrganizationCreate,
    OrganizationMembershipRead,
    OrganizationRead,
    PackageCreate,
    PackageRead,
    PackageWorkflowResponse,
    ProductCategoryParameterRead,
    ProductCategoryRead,
    ProjectCreate,
    ProjectRead,
    QuotationBatchEntry,
    QuotationBatchResponse,
    RequirementCreate,
    RfqResponse,
    TechnicalClarificationCreate,
    TechnicalClarificationRead,
    TechnicalDeviationCreate,
    TechnicalDeviationRead,
    TechnicalStatusUpdate,
    TokenResponse,
    UserRead,
    UserRegister,
    VendorDocumentRead,
)
from freellmpool.api.security import hash_password
from freellmpool.api.web import web_app
from freellmpool.industrial import (
    ClaimStatus,
    CommercialValue,
    DocumentPage,
    EvidenceProvenance,
    VendorValue,
    build_evidence_register,
    build_matrix,
    build_report,
    document_text,
    extract_claim_candidates,
    extract_document_pages,
)
from freellmpool.industrial import Requirement as EngineRequirement
from freellmpool.industrial_report import render_engineering_report
from freellmpool.product_categories import get_product_category, list_product_categories

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


def _vendor_key(vendor_name: str) -> str:
    """Normalize a vendor name for duplicate-offer detection."""
    return " ".join(vendor_name.split()).casefold()


def _find_duplicate_offer(
    package: ProcurementPackage,
    vendor_key: str,
    technical_revision: str,
) -> VendorOffer | None:
    """Return an existing offer with the same normalized vendor and revision."""
    for existing in package.offers:
        if (
            _vendor_key(existing.vendor_name) == vendor_key
            and existing.technical_revision == technical_revision
        ):
            return existing
    return None


def _safe_filename(raw: str | None) -> str:
    """Reduce an uploaded filename to a safe basename without path components."""
    name = Path((raw or "").replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        raise HTTPException(status_code=422, detail="a valid filename is required")
    if len(name) > 255:
        raise HTTPException(status_code=422, detail="filename must be at most 255 characters")
    return name


def _auto_create_document_claims(
    db: Session,
    offer: VendorOffer,
    document: VendorDocument,
    pages: list[DocumentPage],
) -> int:
    """Create deterministic, provenance-backed claims from explicit quotation fields."""
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in offer.package.requirements
    ]
    candidates = extract_claim_candidates(pages, requirements)
    for candidate in candidates:
        db.add(
            VendorClaim(
                offer_id=offer.id,
                parameter=candidate.parameter,
                value=candidate.value,
                evidence=candidate.evidence,
                claim_status="VERIFIED",
                source_document_id=document.id,
                source_page=candidate.page,
                source_section=candidate.section,
                source_table=candidate.table,
                source_cell=candidate.cell,
            )
        )
    return len(candidates)


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


@app.get("/product-categories", response_model=list[ProductCategoryRead])
def list_categories(
    user: User = Depends(get_current_user),  # noqa: B008
) -> list[ProductCategoryRead]:
    """Return the configured product-category templates available to the tenant."""
    del user
    return [
        ProductCategoryRead(
            key=category.key,
            name=category.name,
            description=category.description,
            parameters=[
                ProductCategoryParameterRead(
                    key=parameter.key,
                    label=parameter.label,
                    mandatory=parameter.mandatory,
                    unit=parameter.unit,
                )
                for parameter in category.parameters
            ],
        )
        for category in list_product_categories()
    ]


@app.get("/product-categories/{category_key}", response_model=ProductCategoryRead)
def get_category(
    category_key: str,
    user: User = Depends(get_current_user),  # noqa: B008
) -> ProductCategoryRead:
    """Return one product-category template by key."""
    del user
    category = get_product_category(category_key)
    if category is None:
        raise HTTPException(status_code=404, detail="product category not found")
    return ProductCategoryRead(
        key=category.key,
        name=category.name,
        description=category.description,
        parameters=[
            ProductCategoryParameterRead(
                key=parameter.key,
                label=parameter.label,
                mandatory=parameter.mandatory,
                unit=parameter.unit,
            )
            for parameter in category.parameters
        ],
    )


@app.get("/", include_in_schema=False)
def web_review_app() -> Response:
    """Serve the browser-based procurement workspace."""
    return web_app()


@app.get("/projects", response_model=list[ProjectRead])
def list_projects(
    organization_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ProjectRead]:
    """List projects visible to the authenticated tenant member."""
    if not is_member(db, user.id, organization_id):
        raise HTTPException(status_code=404, detail="organization not found")
    rows = db.scalars(
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.id)
    ).all()
    return [ProjectRead.model_validate(row) for row in rows]


@app.get("/packages", response_model=list[PackageRead])
def list_packages(
    project_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[PackageRead]:
    """List procurement packages visible through the user's project tenant."""
    project = db.get(Project, project_id)
    if project is None or not is_member(db, user.id, project.organization_id):
        raise HTTPException(status_code=404, detail="project not found")
    rows = db.scalars(
        select(ProcurementPackage)
        .where(ProcurementPackage.project_id == project_id)
        .order_by(ProcurementPackage.id)
    ).all()
    return [PackageRead.model_validate(row) for row in rows]



def _audit(
    db: Session,
    package: ProcurementPackage,
    user: User,
    event_type: str,
    offer: VendorOffer | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
) -> None:
    db.add(
        ProcurementAuditEvent(
            package_id=package.id,
            offer_id=offer.id if offer is not None else None,
            actor_user_id=user.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            note=note,
        )
    )


@app.post("/packages/{package_id}/decision", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
def create_or_update_decision(
    package_id: int,
    payload: DecisionCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementDecision:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    if not package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is not open")
    offer = db.get(VendorOffer, payload.selected_offer_id)
    if offer is None or offer.package_id != package_id:
        raise HTTPException(status_code=404, detail="selected offer not found")
    if offer.technical_status not in {"ACCEPTED", "ACCEPTED_WITH_DEVIATION"}:
        raise HTTPException(status_code=409, detail="selected offer is not technically accepted")
    if offer.commercial_status != "COMPLETED":
        raise HTTPException(status_code=409, detail="selected offer commercial evaluation is not completed")
    decision = db.scalar(select(ProcurementDecision).where(ProcurementDecision.package_id == package_id))
    previous_offer_id: int | None = None
    if decision is None:
        decision = ProcurementDecision(
            package_id=package_id,
            selected_offer_id=offer.id,
            decision_status="FINAL",
            rationale=payload.rationale.strip(),
            decided_by_user_id=user.id,
        )
        db.add(decision)
        event_type = "FINAL_DECISION_CREATED"
    else:
        previous_offer_id = decision.selected_offer_id
        decision.selected_offer_id = offer.id
        decision.decision_status = "FINAL"
        decision.rationale = payload.rationale.strip()
        decision.decided_by_user_id = user.id
        decision.updated_at = datetime.now(UTC)
        event_type = "FINAL_DECISION_UPDATED"
    _audit(
        db, package, user, event_type, offer,
        from_status=str(previous_offer_id) if previous_offer_id is not None else None,
        to_status=str(offer.id), note=payload.rationale.strip(),
    )
    db.commit()
    db.refresh(decision)
    return decision


@app.get("/packages/{package_id}/decision", response_model=DecisionRead)
def read_decision(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementDecision:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    decision = db.scalar(select(ProcurementDecision).where(ProcurementDecision.package_id == package_id))
    if decision is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return decision


@app.get("/packages/{package_id}/audit", response_model=list[AuditEventRead])
def package_audit(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[ProcurementAuditEvent]:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    return list(
        db.scalars(
            select(ProcurementAuditEvent)
            .where(ProcurementAuditEvent.package_id == package_id)
            .order_by(ProcurementAuditEvent.id)
        )
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "industrial-rfq-intelligence"}


@app.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegister, db: Session = Depends(get_db)  # noqa: B008
) -> User:
    email = payload.email.strip().casefold()
    if "@" not in email or email.startswith("@") or email.endswith("@") or " " in email:
        raise HTTPException(status_code=422, detail="a valid email address is required")
    existing: User | None = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="email is already registered")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, db: Session = Depends(get_db)  # noqa: B008
) -> TokenResponse:
    user = authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _session, token = issue_session(db, user)
    db.commit()
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@app.get("/auth/me", response_model=CurrentUserRead)
def current_user(
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> CurrentUserRead:
    rows = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(
            OrganizationMembership,
            Organization.id == OrganizationMembership.organization_id,
        )
        .where(OrganizationMembership.user_id == user.id)
    ).all()
    return CurrentUserRead(
        id=user.id,
        email=user.email,
        organizations=[
            OrganizationMembershipRead(
                organization_id=organization.id,
                name=organization.name,
                role=role,
            )
            for organization, role in rows
        ],
    )


@app.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Organization:
    organization = Organization(name=payload.name.strip())
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role="OWNER",
        )
    )
    now = datetime.now(UTC)
    db.add(
        OrganizationSubscription(
            organization_id=organization.id,
            plan_key="STARTER",
            status="ACTIVE",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
    )
    db.commit()
    db.refresh(organization)
    return organization


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Project:
    # The client may suggest an organization, but membership is always
    # verified server-side against the authenticated user.
    if not is_member(db, user.id, payload.organization_id):
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
    payload: PackageCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementPackage:
    if payload.mode not in {"STANDARD", "PROJECT_EPC"}:
        raise HTTPException(status_code=422, detail="mode must be STANDARD or PROJECT_EPC")
    project = db.get(Project, payload.project_id)
    if project is None or not is_member(db, user.id, project.organization_id):
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
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> RfqResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
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
    package_id: int,
    payload: OfferCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    _require_technical_stage_open(package)
    vendor_name = payload.vendor_name.strip()
    technical_revision = payload.technical_revision.strip()
    vendor_key = _vendor_key(vendor_name)
    if _find_duplicate_offer(package, vendor_key, technical_revision) is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"an offer for {vendor_name} revision {technical_revision} "
                "already exists for this package"
            ),
        )
    offer = VendorOffer(
        package_id=package_id,
        vendor_name=vendor_name,
        manufacturer=payload.manufacturer,
        model=payload.model,
        part_number=payload.part_number,
        vendor_key=vendor_key,
        technical_revision=technical_revision,
        price=payload.price,
        currency=payload.currency,
        lead_time=payload.lead_time,
        warranty=payload.warranty,
        source_text=payload.source_text,
    )
    db.add(offer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="an offer for this vendor and revision already exists",
        ) from exc
    db.refresh(offer)
    return offer


@app.get("/packages/{package_id}/offers", response_model=list[OfferRead])
def list_package_offers(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[OfferRead]:
    """List the auditable offer/revision history for a package."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    reveal_commercial = package.commercial_evaluation_open or package.mode != "PROJECT_EPC"
    return [
        OfferRead(
            id=offer.id,
            package_id=offer.package_id,
            parent_offer_id=offer.parent_offer_id,
            vendor_name=offer.vendor_name,
            manufacturer=offer.manufacturer,
            model=offer.model,
            part_number=offer.part_number,
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
    "/packages/{package_id}/quotations/batch",
    response_model=QuotationBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def batch_ingest_quotations(
    package_id: int,
    entries: str = Form(...),  # noqa: B008
    files: list[UploadFile] = File(...),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> QuotationBatchResponse:
    """Ingest several vendor quotations and their documents in one atomic batch.

    Every entry is validated (tenancy, workflow stage, duplicate vendors,
    file type and size) before any row is written: a batch either lands
    completely or not at all.
    """
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    _require_technical_stage_open(package)
    try:
        parsed_entries = json.loads(entries)
        batch: list[QuotationBatchEntry] = [
            QuotationBatchEntry.model_validate(item) for item in parsed_entries
        ]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="entries must be a JSON array of quotation objects",
        ) from exc
    if not batch or len(batch) != len(files):
        raise HTTPException(
            status_code=422,
            detail="entries and files must be non-empty and match one-to-one",
        )
    # Duplicate detection spans the batch and the existing offers, and runs
    # before any write so a conflicting batch persists nothing.
    seen: set[tuple[str, str]] = set()
    for entry in batch:
        vendor_name = entry.vendor_name.strip()
        revision = entry.technical_revision.strip()
        if not vendor_name or not revision:
            raise HTTPException(
                status_code=422, detail="vendor_name and technical_revision must not be blank"
            )
        key = (_vendor_key(vendor_name), revision)
        if key in seen or _find_duplicate_offer(package, key[0], key[1]) is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"an offer for {vendor_name} revision {revision} "
                    "already exists for this package"
                ),
            )
        seen.add(key)
    # Validate and extract every file before touching the database.
    prepared: list[tuple[QuotationBatchEntry, str, str | None, list[DocumentPage]]] = []
    for entry, file in zip(batch, files, strict=True):
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
        prepared.append((entry, filename, content_type, pages))
    # Persist all offers and documents in a single transaction.
    offers: list[VendorOffer] = []
    documents: list[VendorDocument] = []
    for entry, filename, content_type, pages in prepared:
        offer = VendorOffer(
            package_id=package_id,
            vendor_name=entry.vendor_name.strip(),
            manufacturer=entry.manufacturer,
            model=entry.model,
            part_number=entry.part_number,
            vendor_key=_vendor_key(entry.vendor_name),
            technical_revision=entry.technical_revision.strip(),
            price=entry.price,
            currency=entry.currency,
            lead_time=entry.lead_time,
            warranty=entry.warranty,
            source_text=entry.source_text,
        )
        document = VendorDocument(
            offer=offer,
            filename=filename,
            content_type=content_type,
            document_type="VENDOR_OFFER",
            page_count=len(pages),
            extracted_text=document_text(pages),
            pages=[VendorDocumentPage(page_number=page.page, text=page.text) for page in pages],
        )
        offers.append(offer)
        documents.append(document)
        db.add(offer)
    db.flush()
    for offer, document, prepared_item in zip(
        offers, documents, prepared, strict=True
    ):
        _auto_create_document_claims(db, offer, document, prepared_item[3])
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="an offer for this vendor and revision already exists",
        ) from exc
    for offer in offers:
        db.refresh(offer)
    return QuotationBatchResponse(
        package_id=package.id,
        offers=[OfferRead.model_validate(offer) for offer in offers],
        document_ids=[document.id for document in documents],
    )


@app.post(
    "/offers/{offer_id}/revisions",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_offer_revision(
    offer_id: int,
    payload: OfferRevisionCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    """Create the next technical revision without mutating earlier ones."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    revision = payload.technical_revision.strip()
    if not revision:
        raise HTTPException(status_code=422, detail="technical_revision must not be empty")
    vendor_key = _vendor_key(offer.vendor_name)
    if _find_duplicate_offer(offer.package, vendor_key, revision) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"revision {revision} already exists for {offer.vendor_name}",
        )
    revision_offer = VendorOffer(
        package_id=offer.package_id,
        parent_offer_id=offer.id,
        vendor_name=offer.vendor_name,
        manufacturer=offer.manufacturer,
        model=offer.model,
        part_number=offer.part_number,
        vendor_key=vendor_key,
        technical_revision=revision,
        source_text=payload.source_text,
    )
    db.add(revision_offer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"revision {revision} already exists for {offer.vendor_name}",
        ) from exc
    db.refresh(revision_offer)
    return revision_offer


@app.post("/offers/{offer_id}/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
def add_claim(
    offer_id: int,
    payload: ClaimCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorClaim:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
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
        if payload.source_page is not None and payload.source_page > document.page_count:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"source_page must be between 1 and {document.page_count} "
                    "for this document"
                ),
            )
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
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalDeviation:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    severity = payload.severity.strip().upper()
    deviation_status = payload.status.strip().upper()
    if severity not in {"MINOR", "MAJOR"}:
        raise HTTPException(status_code=422, detail="severity must be MINOR or MAJOR")
    if deviation_status != "OPEN":
        raise HTTPException(
            status_code=422,
            detail=(
                "deviations must be created with status OPEN; "
                "use the resolve endpoint to record resolution"
            ),
        )
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
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarification:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    _require_technical_stage_open(offer.package)
    clarification_status = payload.status.strip().upper()
    if clarification_status not in {"OPEN", "ANSWERED"}:
        raise HTTPException(
            status_code=422,
            detail=(
                "clarifications must be created OPEN or ANSWERED; "
                "use the close endpoint to record closure"
            ),
        )
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
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalDeviation:
    deviation = db.get(TechnicalDeviation, deviation_id)
    if (
        deviation is None
        or not is_member(db, user.id, deviation.offer.package.project.organization_id)
    ):
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
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarification:
    clarification = db.get(TechnicalClarification, clarification_id)
    if (
        clarification is None
        or not is_member(
            db, user.id, clarification.offer.package.project.organization_id
        )
    ):
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
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorDocument:
    """Ingest an untrusted vendor document as extracted, provenance-tagged text."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
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
    db.flush()
    _auto_create_document_claims(db, offer, document, pages)
    db.commit()
    db.refresh(document)
    return document


@app.get("/documents/{document_id}", response_model=VendorDocumentRead)
def read_document(
    document_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorDocument:
    document = db.get(VendorDocument, document_id)
    if (
        document is None
        or not is_member(db, user.id, document.offer.package.project.organization_id)
    ):
        raise HTTPException(status_code=404, detail="document not found")
    return document


@app.get("/offers/{offer_id}/deviations", response_model=list[TechnicalDeviationRead])
def list_offer_deviations(
    offer_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TechnicalDeviation]:
    """List the auditable technical deviations for one vendor offer."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    return sorted(offer.deviations, key=lambda item: item.id)


@app.get("/offers/{offer_id}/clarifications", response_model=list[TechnicalClarificationRead])
def list_offer_clarifications(
    offer_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> list[TechnicalClarification]:
    """List the auditable technical clarifications for one vendor offer."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    return sorted(offer.clarifications, key=lambda item: item.id)


@app.get("/packages/{package_id}/workflow", response_model=PackageWorkflowResponse)
def package_workflow(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> PackageWorkflowResponse:
    """Return the current EPC technical/commercial workflow gate state."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    status_counts: dict[str, int] = {}
    for offer in package.offers:
        status_counts[offer.technical_status] = status_counts.get(offer.technical_status, 0) + 1
    return PackageWorkflowResponse(
        package_id=package.id,
        mode=package.mode,
        technical_bid_locked=package.technical_bid_locked,
        commercial_evaluation_open=package.commercial_evaluation_open,
        offer_count=len(package.offers),
        technical_status_counts=status_counts,
        open_deviation_count=sum(
            item.status == "OPEN" for offer in package.offers for item in offer.deviations
        ),
        open_clarification_count=sum(
            item.status == "OPEN" for offer in package.offers for item in offer.clarifications
        ),
    )


@app.post("/offers/{offer_id}/technical-status", response_model=OfferRead)
def update_technical_status(
    offer_id: int,
    payload: TechnicalStatusUpdate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
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
    old_status = offer.technical_status
    offer.technical_status = status_value
    _audit(db, offer.package, user, "TECHNICAL_STATUS_CHANGED", offer, old_status, status_value)
    db.commit()
    db.refresh(offer)
    return offer


@app.post("/packages/{package_id}/technical-lock", response_model=PackageRead)
def lock_technical_bid(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    if not package.offers:
        raise HTTPException(status_code=409, detail="at least one vendor offer is required")
    blocking_statuses = {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED"}
    blocking = [offer.vendor_name for offer in package.offers if offer.technical_status in blocking_statuses]
    unresolved = [
        f"{offer.vendor_name}: unresolved technical issue"
        for offer in package.offers
        if any(item.status != "RESOLVED" for item in offer.deviations)
        or any(item.status != "CLOSED" for item in offer.clarifications)
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
    _audit(db, package, user, "TECHNICAL_BID_LOCKED", to_status="LOCKED")
    db.commit()
    db.refresh(package)
    return package


@app.post("/packages/{package_id}/commercial-open", response_model=PackageRead)
def open_commercial_evaluation(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ProcurementPackage:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    if package.mode == "PROJECT_EPC" and not package.technical_bid_locked:
        raise HTTPException(
            status_code=409,
            detail="technical bid must be locked before commercial evaluation",
        )
    package.commercial_evaluation_open = True
    _audit(db, package, user, "COMMERCIAL_EVALUATION_OPENED", to_status="OPEN")
    for offer in package.offers:
        if offer.technical_status in {"ACCEPTED", "ACCEPTED_WITH_DEVIATION"}:
            offer.commercial_status = "OPEN"
        else:
            offer.commercial_status = "LOCKED"
    db.commit()
    db.refresh(package)
    return package


@app.post("/offers/{offer_id}/commercial-status", response_model=OfferRead)
def update_commercial_status(
    offer_id: int,
    payload: CommercialStatusUpdate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    """Advance commercial evaluation only after the package commercial gate opens."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    package = offer.package
    if not package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is not open")
    if offer.commercial_status == "LOCKED":
        raise HTTPException(status_code=409, detail="commercial evaluation is locked for this offer")
    requested = payload.status.strip().upper()
    if requested not in {"OPEN", "IN_REVIEW", "COMPLETED"}:
        raise HTTPException(status_code=422, detail="invalid commercial status")
    if offer.technical_status not in {"ACCEPTED", "ACCEPTED_WITH_DEVIATION"}:
        raise HTTPException(status_code=409, detail="only technically accepted offers can be commercially evaluated")
    allowed_next = {
        "OPEN": {"OPEN", "IN_REVIEW"},
        "IN_REVIEW": {"IN_REVIEW", "COMPLETED"},
        "COMPLETED": {"COMPLETED"},
    }
    if requested not in allowed_next[offer.commercial_status]:
        raise HTTPException(
            status_code=409,
            detail=f"invalid commercial status transition from {offer.commercial_status} to {requested}",
        )
    old_status = offer.commercial_status
    offer.commercial_status = requested
    _audit(db, package, user, "COMMERCIAL_STATUS_CHANGED", offer, old_status, requested)
    db.commit()
    db.refresh(offer)
    return offer


@app.get("/packages/{package_id}/commercial-comparison", response_model=CommercialComparisonResponse)
def commercial_comparison(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> CommercialComparisonResponse:
    """Return the commercial view after the EPC commercial gate is opened."""
    package = db.get(ProcurementPackage, package_id)
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

    commercial_values = [
        CommercialValue(
            vendor=offer.vendor_name,
            price=offer.price or "",
            currency=offer.currency or "",
            lead_time=offer.lead_time or "",
            warranty=offer.warranty or "",
            payment_terms="",
            evidence=offer.source_text or "",
            claim_status="UNVERIFIED",
        )
        for offer in package.offers
        if any(
            value
            for value in (offer.price, offer.currency, offer.lead_time, offer.warranty, offer.source_text)
        )
    ]
    return build_report(requirements, vendor_values, commercial_values)


@app.get("/packages/{package_id}/report/markdown")
def package_report_markdown(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> Response:
    """Export the package review as an engineer-readable Markdown document."""
    report = package_report(package_id, user, db)
    markdown = render_engineering_report(report)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="rfq-review-package-{package_id}.md"'
        },
    )