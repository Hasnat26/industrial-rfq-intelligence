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
    PackageEvaluationSettings,
    ProcurementAuditEvent,
    ProcurementDecision,
    ProcurementPackage,
    Project,
    Requirement,
    RfqRevision,
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
    DecisionSupportResponse,
    DecisionSupportRowRead,
    DecisionSupportVendorRead,
    EngineeringDecisionSummaryRead,
    EngineeringVendorProfileRead,
    EvaluationWeightingRead,
    EvaluationWeightingUpdate,
    EvidenceResponse,
    EvidenceRow,
    IntegratedEvaluationResponse,
    IntegratedVendorEvaluationRead,
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
    RfqRevisionCreate,
    RfqRevisionRead,
    TechnicalClarificationAnswer,
    TechnicalClarificationCreate,
    TechnicalClarificationGapRead,
    TechnicalClarificationPackageRead,
    TechnicalClarificationRead,
    TechnicalDeviationCreate,
    TechnicalDeviationRead,
    TechnicalEvaluationResponse,
    TechnicalEvaluationRow,
    TechnicalStatusUpdate,
    TokenResponse,
    UserRead,
    UserRegister,
    VendorDocumentRead,
)
from freellmpool.api.security import hash_password
from freellmpool.api.web import web_app
from freellmpool.decision_support import build_decision_support
from freellmpool.engineering_decision import build_engineering_decision_summary
from freellmpool.industrial import (
    ClaimStatus,
    CommercialValue,
    DocumentPage,
    EvidenceProvenance,
    VendorValue,
    build_commercial_risk_review,
    build_evidence_register,
    build_matrix,
    build_report,
    document_text,
    extract_claim_candidates,
    extract_document_pages,
)
from freellmpool.industrial import Requirement as EngineRequirement
from freellmpool.industrial_report import render_engineering_report
from freellmpool.integrated_evaluation import build_integrated_evaluation
from freellmpool.product_categories import get_product_category, list_product_categories
from freellmpool.technical_clarification import build_technical_clarification_package
from freellmpool.technical_comparison import compare_technical_requirements

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


def _require_current_rfq_offer(package: ProcurementPackage, offer: VendorOffer) -> None:
    if package.current_rfq_revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    if offer.rfq_revision_id != package.current_rfq_revision_id:
        raise HTTPException(status_code=409, detail="offer belongs to a superseded RFQ revision")


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
        if item.rfq_revision_id == offer.rfq_revision_id
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


def _active_vendor_offers(package: ProcurementPackage) -> list[VendorOffer]:
    """Return leaf offers that target the package's current RFQ revision."""
    current_revision_id = package.current_rfq_revision_id
    return [
        offer
        for offer in package.offers
        if not offer.revisions and offer.rfq_revision_id == current_revision_id
    ]


def _technical_comparison_rows(package: ProcurementPackage) -> list[dict[str, object]]:
    """Build the canonical vendor/requirement comparison with revision carry-forward."""
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in package.requirements
        if item.rfq_revision_id == package.current_rfq_revision_id
    ]
    grouped: dict[str, list[VendorOffer]] = {}
    for offer in package.offers:
        if offer.rfq_revision_id == package.current_rfq_revision_id:
            grouped.setdefault(offer.vendor_key, []).append(offer)

    vendor_values: list[VendorValue] = []
    vendor_names: list[str] = []
    claim_parameters_by_vendor: dict[str, set[str]] = {}
    for _vendor_key, chain in grouped.items():
        ordered = sorted(chain, key=lambda item: item.id)
        latest = ordered[-1]
        vendor_names.append(latest.vendor_name)
        claims_by_parameter: dict[str, list[VendorClaim]] = {}
        for offer in ordered:
            claims_this_revision: dict[str, list[VendorClaim]] = {}
            for claim in offer.claims:
                claims_this_revision.setdefault(claim.parameter.casefold().strip(), []).append(claim)
            for parameter, claims in claims_this_revision.items():
                claims_by_parameter[parameter] = claims
        parameters = claim_parameters_by_vendor.setdefault(latest.vendor_name, set())
        for claims in claims_by_parameter.values():
            for claim in claims:
                vendor_values.append(
                    VendorValue(
                        latest.vendor_name,
                        claim.parameter,
                        claim.value,
                        claim.evidence,
                        _claim_status(claim.claim_status),
                    )
                )
                parameters.add(claim.parameter.casefold().strip())

    matrix = build_matrix(requirements, vendor_values, vendors=vendor_names)
    rows: list[dict[str, object]] = []
    for row in matrix:
        status = str(row["status"])
        if str(row["parameter"]).casefold().strip() not in claim_parameters_by_vendor.get(
            str(row["vendor"]), set()
        ):
            status = "UNVERIFIED"
        rows.append(
            {
                "vendor": row["vendor"],
                "parameter": row["parameter"],
                "required": row["required"],
                "offered": None if row["offered"] == "MISSING" else row["offered"],
                "status": status,
            }
        )
    return rows


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
    _require_current_rfq_offer(package, offer)
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="a final decision already exists for this package",
        ) from exc
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
    db.add(package)
    db.flush()

    rfq_revision = RfqRevision(
        package_id=package.id,
        revision="R1",
        status="CURRENT",
        reason="Initial RFQ baseline",
        created_by_user_id=user.id,
    )
    db.add(rfq_revision)
    db.flush()
    package.current_rfq_revision_id = rfq_revision.id

    db.add(
        PackageEvaluationSettings(
            package=package,
            technical_weight=70.0,
            commercial_weight=30.0,
        )
    )
    for item in payload.requirements:
        package.requirements.append(
            Requirement(
                rfq_revision=rfq_revision,
                tag=item.tag.strip(),
                parameter=item.parameter.strip(),
                required_value=item.required_value.strip(),
                requirement_type=item.requirement_type,
                acceptance_rule=item.acceptance_rule,
            )
        )
    db.commit()
    db.refresh(package)
    return package


@app.post(
    "/packages/{package_id}/rfq-revisions",
    response_model=RfqRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rfq_revision(
    package_id: int,
    payload: RfqRevisionCreate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> RfqRevision:
    """Create an immutable customer RFQ revision before technical lock."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    _require_technical_stage_open(package)
    current_id = package.current_rfq_revision_id
    if current_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    current = db.get(RfqRevision, current_id)
    if current is None or current.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="reason must not be empty")
    requirements = payload.requirements
    tags: set[str] = set()
    for item in requirements:
        tag = item.tag.strip()
        parameter = item.parameter.strip()
        required_value = item.required_value.strip()
        if not tag or not parameter or not required_value:
            raise HTTPException(status_code=422, detail="RFQ requirement fields must not be blank")
        normalized_tag = tag.casefold()
        if normalized_tag in tags:
            raise HTTPException(status_code=422, detail="RFQ requirement tags must be unique")
        tags.add(normalized_tag)
    try:
        revision_number = int(current.revision.removeprefix("R")) + 1
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="current RFQ revision has an invalid sequence") from exc
    revision_name = f"R{revision_number}"
    previous_active_offers = _active_vendor_offers(package)
    current.status = "SUPERSEDED"
    revision = RfqRevision(
        package_id=package.id,
        revision=revision_name,
        status="CURRENT",
        reason=reason,
        created_by_user_id=user.id,
        supersedes_revision_id=current.id,
    )
    db.add(revision)
    db.flush()
    for item in requirements:
        revision.requirements.append(
            Requirement(
                package_id=package.id,
                rfq_revision_id=revision.id,
                tag=item.tag.strip(),
                parameter=item.parameter.strip(),
                required_value=item.required_value.strip(),
                requirement_type=item.requirement_type.strip().upper(),
                acceptance_rule=item.acceptance_rule.strip() if item.acceptance_rule else None,
            )
        )
    package.current_rfq_revision_id = revision.id
    for offer in previous_active_offers:
        old_status = offer.technical_status
        offer.technical_status = "SUPERSEDED"
        _audit(
            db,
            package,
            user,
            "RFQ_REVISION_SUPERSEDED_OFFER",
            offer,
            from_status=old_status,
            to_status="SUPERSEDED",
            note=f"Superseded by RFQ {revision_name}",
        )
    _audit(
        db,
        package,
        user,
        "RFQ_REVISION_CREATED",
        from_status=current.revision,
        to_status=revision_name,
        note=reason,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"RFQ revision {revision_name} already exists",
        ) from exc
    db.refresh(revision)
    return revision


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
        if item.rfq_revision_id == package.current_rfq_revision_id
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
    if package.current_rfq_revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    offer = VendorOffer(
        package_id=package_id,
        rfq_revision_id=package.current_rfq_revision_id,
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
    db.flush()
    _audit(
        db,
        package,
        user,
        "TECHNICAL_OFFER_CREATED",
        offer=offer,
        from_status=None,
        to_status=offer.technical_status,
        note=f"Offer {offer.vendor_name} revision {offer.technical_revision} created",
    )
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
        if package.current_rfq_revision_id is None:
            raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
        offer = VendorOffer(
            package_id=package_id,
            rfq_revision_id=package.current_rfq_revision_id,
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
    _audit(db, package, user, "QUOTATION_BATCH_INGESTED", to_status=str(len(offers)), note="; ".join(f"{offer.vendor_name} revision {offer.technical_revision}" for offer in offers))
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
    _require_current_rfq_offer(offer.package, offer)
    if offer.revisions:
        raise HTTPException(status_code=409, detail="use the latest technical revision for resubmission")
    revision = payload.technical_revision.strip()
    if not revision:
        raise HTTPException(status_code=422, detail="technical_revision must not be empty")
    vendor_key = _vendor_key(offer.vendor_name)
    if _find_duplicate_offer(offer.package, vendor_key, revision) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"revision {revision} already exists for {offer.vendor_name}",
        )
    if offer.package.current_rfq_revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision_offer = VendorOffer(
        package_id=offer.package_id,
        rfq_revision_id=offer.package.current_rfq_revision_id,
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
    db.flush()
    _audit(
        db,
        offer.package,
        user,
        "TECHNICAL_OFFER_REVISION_CREATED",
        offer=revision_offer,
        from_status=offer.technical_revision,
        to_status=revision,
        note=f"Technical revision created from {offer.technical_revision}",
    )
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


@app.post(
    "/offers/{offer_id}/technical-resubmission",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
async def resubmit_technical_offer(
    offer_id: int,
    technical_revision: str = Form(...),  # noqa: B008
    file: UploadFile = File(...),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> VendorOffer:
    """Create an auditable vendor technical resubmission with a new revision and document."""
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    package = offer.package
    _require_technical_stage_open(package)
    _require_current_rfq_offer(package, offer)
    if offer.revisions:
        raise HTTPException(status_code=409, detail="use the latest technical revision for resubmission")
    revision = technical_revision.strip()
    if not revision:
        raise HTTPException(status_code=422, detail="technical_revision must not be empty")
    if _find_duplicate_offer(package, _vendor_key(offer.vendor_name), revision) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"revision {revision} already exists for {offer.vendor_name}",
        )
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

    if package.current_rfq_revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    offer.technical_status = "SUPERSEDED"
    revision_offer = VendorOffer(
        package_id=offer.package_id,
        rfq_revision_id=package.current_rfq_revision_id,
        parent_offer_id=offer.id,
        vendor_name=offer.vendor_name,
        manufacturer=offer.manufacturer,
        model=offer.model,
        part_number=offer.part_number,
        vendor_key=_vendor_key(offer.vendor_name),
        technical_revision=revision,
        technical_status="IN_REVIEW",
        source_text=document_text(pages),
    )
    document = VendorDocument(
        offer=revision_offer,
        filename=filename,
        content_type=content_type,
        document_type="VENDOR_TECHNICAL_RESUBMISSION",
        page_count=len(pages),
        extracted_text=document_text(pages),
        pages=[VendorDocumentPage(page_number=page.page, text=page.text) for page in pages],
    )
    db.add(revision_offer)
    db.flush()
    _auto_create_document_claims(db, revision_offer, document, pages)
    _audit(
        db,
        package,
        user,
        "TECHNICAL_OFFER_RESUBMITTED",
        revision_offer,
        from_status=offer.technical_revision,
        to_status=revision,
        note=f"Technical resubmission uploaded as {filename}",
    )
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
    _require_current_rfq_offer(offer.package, offer)
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
    db.flush()
    _audit(
        db,
        offer.package,
        user,
        "VENDOR_CLAIM_CREATED",
        offer=offer,
        from_status=None,
        to_status=claim_status,
        note=f"Claim created for {claim.parameter.strip()}",
    )
    db.commit()
    db.refresh(claim)
    return claim


@app.get(
    "/offers/{offer_id}/technical-clarification-package",
    response_model=TechnicalClarificationPackageRead,
)
def preview_technical_clarification(
    offer_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarificationPackageRead:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.revisions:
        raise HTTPException(status_code=409, detail="use the latest technical revision for clarification")
    _require_current_rfq_offer(offer.package, offer)
    evaluation = _technical_evaluation_rows(offer.package, db)
    rows = [
        row.model_dump()
        for row in evaluation.rows
        if row.offer_id == offer.id
    ]
    package = build_technical_clarification_package(offer.vendor_name, offer.technical_revision, rows)
    if not package.gaps:
        raise HTTPException(status_code=409, detail="no technical clarification is required for this offer")
    return TechnicalClarificationPackageRead(
        offer_id=offer.id,
        vendor=package.vendor,
        technical_revision=package.technical_revision,
        clarification_ids=[
            item.id for item in sorted(offer.clarifications, key=lambda item: item.id)
            if item.status != "CLOSED"
        ],
        gaps=[
            TechnicalClarificationGapRead(
                parameter=item.parameter,
                required=item.required,
                offered=item.offered,
                status=item.status,
                request=item.request,
                rfq_revision_id=item.rfq_revision_id,
                requirement_id=item.requirement_id,
                gap_type=item.gap_type,
                evidence=item.evidence,
            )
            for item in package.gaps
        ],
        subject=package.subject,
        body=package.body,
    )


@app.post(
    "/offers/{offer_id}/technical-clarification-request",
    response_model=TechnicalClarificationPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_technical_clarification_request(
    offer_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalClarificationPackageRead:
    offer = db.get(VendorOffer, offer_id)
    if offer is None or not is_member(db, user.id, offer.package.project.organization_id):
        raise HTTPException(status_code=404, detail="offer not found")
    if offer.revisions:
        raise HTTPException(status_code=409, detail="use the latest technical revision for clarification")
    _require_current_rfq_offer(offer.package, offer)
    _require_technical_stage_open(offer.package)
    if offer.technical_status not in {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED"}:
        raise HTTPException(
            status_code=409,
            detail="technical clarification cannot be requested from the current technical status",
        )
    evaluation = _technical_evaluation_rows(offer.package, db)
    rows = [
        row.model_dump()
        for row in evaluation.rows
        if row.offer_id == offer.id
    ]
    package = build_technical_clarification_package(offer.vendor_name, offer.technical_revision, rows)
    if not package.gaps:
        raise HTTPException(status_code=409, detail="no technical clarification is required for this offer")
    existing = {item.question.strip() for item in offer.clarifications if item.status != "CLOSED"}
    clarification_ids: list[int] = []
    for gap in package.gaps:
        if gap.request in existing:
            continue
        clarification = TechnicalClarification(
            offer_id=offer.id,
            rfq_revision_id=gap.rfq_revision_id,
            requirement_id=gap.requirement_id,
            gap_type=gap.gap_type,
            evaluated_offered=gap.offered,
            evaluation_status=gap.status,
            evaluation_evidence=gap.evidence,
            question=gap.request,
            status="OPEN",
        )
        db.add(clarification)
        db.flush()
        clarification_ids.append(clarification.id)
    if offer.technical_status != "CLARIFICATION_REQUIRED":
        old_status = offer.technical_status
        offer.technical_status = "CLARIFICATION_REQUIRED"
        _audit(
            db,
            offer.package,
            user,
            "TECHNICAL_CLARIFICATION_REQUESTED",
            offer,
            from_status=old_status,
            to_status="CLARIFICATION_REQUIRED",
            note=package.subject,
        )
    db.commit()
    db.refresh(offer)
    return TechnicalClarificationPackageRead(
        offer_id=offer.id,
        vendor=package.vendor,
        technical_revision=offer.technical_revision,
        clarification_ids=clarification_ids,
        gaps=[
            TechnicalClarificationGapRead(
                parameter=item.parameter,
                required=item.required,
                offered=item.offered,
                status=item.status,
                request=item.request,
                rfq_revision_id=item.rfq_revision_id,
                requirement_id=item.requirement_id,
                gap_type=item.gap_type,
                evidence=item.evidence,
            )
            for item in package.gaps
        ],
        subject=package.subject,
        body=package.body,
    )


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
    _require_current_rfq_offer(offer.package, offer)
    if offer.technical_status in {"ACCEPTED", "ACCEPTED_WITH_DEVIATION", "REJECTED"}:
        raise HTTPException(
            status_code=409,
            detail="technical deviation cannot be created from the current technical status",
        )
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
    _audit(
        db,
        offer.package,
        user,
        "TECHNICAL_DEVIATION_CREATED",
        offer=offer,
        from_status=None,
        to_status=deviation_status,
        note=deviation.description,
    )
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
    _require_current_rfq_offer(offer.package, offer)
    if offer.technical_status not in {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED"}:
        raise HTTPException(
            status_code=409,
            detail="technical clarification cannot be created from the current technical status",
        )
    clarification_status = payload.status.strip().upper()
    if clarification_status not in {"OPEN", "ANSWERED"}:
        raise HTTPException(
            status_code=422,
            detail=(
                "clarifications must be created OPEN or ANSWERED; "
                "use the close endpoint to record closure"
            ),
        )
    if offer.package.current_rfq_revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")

    if clarification_status == "ANSWERED" and not (payload.response or "").strip():
        raise HTTPException(status_code=422, detail="response must not be empty")
    clarification = TechnicalClarification(
        offer_id=offer_id,
        rfq_revision_id=offer.package.current_rfq_revision_id,
        question=payload.question.strip(),
        response=payload.response,
        status=clarification_status,
    )
    db.add(clarification)
    _audit(
        db,
        offer.package,
        user,
        "CLARIFICATION_CREATED",
        offer=offer,
        from_status=None,
        to_status=clarification_status,
        note=clarification.question.strip(),
    )
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
    _require_current_rfq_offer(deviation.offer.package, deviation.offer)
    if deviation.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    previous_status = deviation.status
    deviation.status = "RESOLVED"
    deviation.resolution = payload.note.strip()
    _audit(
        db,
        deviation.offer.package,
        user,
        "TECHNICAL_DEVIATION_RESOLVED",
        offer=deviation.offer,
        from_status=previous_status,
        to_status="RESOLVED",
        note=deviation.resolution,
    )
    db.commit()
    db.refresh(deviation)
    return deviation


@app.post(
    "/clarifications/{clarification_id}/answer",
    response_model=TechnicalClarificationRead,
)
def answer_clarification(
    clarification_id: int,
    payload: TechnicalClarificationAnswer,
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
    if clarification.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    _require_current_rfq_offer(clarification.offer.package, clarification.offer)
    if clarification.status == "CLOSED":
        raise HTTPException(status_code=409, detail="clarification is already closed")
    if clarification.status != "OPEN":
        raise HTTPException(
            status_code=409,
            detail="clarification must be OPEN before it can be answered",
        )
    response = payload.response.strip()
    if not response:
        raise HTTPException(status_code=422, detail="response must not be empty")
    clarification.response = response
    previous_status = clarification.status
    clarification.status = "ANSWERED"
    _audit(
        db,
        clarification.offer.package,
        user,
        "CLARIFICATION_ANSWERED",
        offer=clarification.offer,
        from_status=previous_status,
        to_status="ANSWERED",
        note=clarification.response,
    )
    db.commit()
    db.refresh(clarification)
    return clarification


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
    if clarification.status != "ANSWERED":
        raise HTTPException(
            status_code=409,
            detail="clarification must be ANSWERED before it can be closed",
        )
    if clarification.offer.package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    _require_current_rfq_offer(clarification.offer.package, clarification.offer)
    previous_status = clarification.status
    clarification.status = "CLOSED"
    clarification.resolution = payload.note.strip()
    _audit(
        db,
        clarification.offer.package,
        user,
        "CLARIFICATION_CLOSED",
        offer=clarification.offer,
        from_status=previous_status,
        to_status="CLOSED",
        note=clarification.resolution,
    )
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
    _require_current_rfq_offer(offer.package, offer)
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
    _audit(
        db,
        offer.package,
        user,
        "VENDOR_DOCUMENT_UPLOADED",
        offer=offer,
        from_status=None,
        to_status=document.document_type,
        note=document.filename,
    )
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
    if package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    active_offers = _active_vendor_offers(package)
    status_counts: dict[str, int] = {}
    for offer in active_offers:
        status_counts[offer.technical_status] = status_counts.get(offer.technical_status, 0) + 1
    return PackageWorkflowResponse(
        package_id=package.id,
        mode=package.mode,
        technical_bid_locked=package.technical_bid_locked,
        commercial_evaluation_open=package.commercial_evaluation_open,
        offer_count=len(active_offers),
        technical_status_counts=status_counts,
        open_deviation_count=sum(
            item.status == "OPEN" for offer in active_offers for item in offer.deviations
        ),
        open_clarification_count=sum(
            item.status == "OPEN" for offer in active_offers for item in offer.clarifications
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
    _require_current_rfq_offer(offer.package, offer)
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
    allowed_next = {
        "PENDING": {            "PENDING",            "IN_REVIEW",            "CLARIFICATION_REQUIRED",            "ACCEPTED",            "ACCEPTED_WITH_DEVIATION",            "REJECTED",        },
        "IN_REVIEW": {
            "IN_REVIEW",
            "CLARIFICATION_REQUIRED",
            "ACCEPTED",
            "ACCEPTED_WITH_DEVIATION",
            "REJECTED",
        },
        "CLARIFICATION_REQUIRED": {
            "CLARIFICATION_REQUIRED",
            "IN_REVIEW",
            "ACCEPTED",
            "ACCEPTED_WITH_DEVIATION",
            "REJECTED",
        },
        "ACCEPTED": {"ACCEPTED"},
        "ACCEPTED_WITH_DEVIATION": {"ACCEPTED_WITH_DEVIATION"},
        "REJECTED": {"REJECTED"},
    }
    old_status = offer.technical_status
    if status_value not in allowed_next[old_status]:
        raise HTTPException(
            status_code=409,
            detail=f"invalid technical status transition from {old_status} to {status_value}",
        )
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
    if package.technical_bid_locked:
        raise HTTPException(status_code=409, detail="technical bid is already locked")
    active_offers = _active_vendor_offers(package)
    if not active_offers:
        raise HTTPException(status_code=409, detail="at least one current vendor offer is required")
    blocking_statuses = {"PENDING", "IN_REVIEW", "CLARIFICATION_REQUIRED"}
    blocking = [offer.vendor_name for offer in active_offers if offer.technical_status in blocking_statuses]
    unresolved = [
        f"{offer.vendor_name}: unresolved technical issue"
        for offer in active_offers
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
    if package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="commercial evaluation is already open")
    if package.mode == "PROJECT_EPC" and not package.technical_bid_locked:
        raise HTTPException(
            status_code=409,
            detail="technical bid must be locked before commercial evaluation",
        )
    package.commercial_evaluation_open = True
    _audit(db, package, user, "COMMERCIAL_EVALUATION_OPENED", to_status="OPEN")
    for offer in _active_vendor_offers(package):
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
    _require_current_rfq_offer(package, offer)
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
        for offer in sorted(_active_vendor_offers(package), key=lambda item: item.id)
        if offer.commercial_status != "LOCKED"
    ]
    return CommercialComparisonResponse(
        package_id=package.id,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )


def _technical_evaluation_rows(
    package: ProcurementPackage,
    db: Session,
) -> TechnicalEvaluationResponse:
    """Evaluate active vendor offers against the package's current RFQ revision."""
    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")

    active_offers = [
        offer
        for offer in _active_vendor_offers(package)
        if offer.rfq_revision_id == revision.id
    ]
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    vendor_values: list[VendorValue] = []
    metadata: dict[str, VendorOffer] = {}
    vendor_names: list[str] = []

    for latest in active_offers:
        metadata[" ".join(latest.vendor_name.casefold().split())] = latest
        vendor_names.append(latest.vendor_name)
        chain: list[VendorOffer] = []
        current: VendorOffer | None = latest
        seen: set[int] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            current = current.parent_offer
        chain.reverse()

        claims_by_parameter: dict[str, list[VendorClaim]] = {}
        for offer in chain:
            claims_this_revision: dict[str, list[VendorClaim]] = {}
            for claim in offer.claims:
                claims_this_revision.setdefault(claim.parameter.casefold().strip(), []).append(claim)
            for parameter, claims in claims_this_revision.items():
                claims_by_parameter[parameter] = claims

        for claims in claims_by_parameter.values():
            for claim in claims:
                vendor_values.append(
                    VendorValue(
                        latest.vendor_name,
                        claim.parameter,
                        claim.value,
                        claim.evidence,
                        _claim_status(claim.claim_status),
                    )
                )

    findings = compare_technical_requirements(
        requirements,
        vendor_values,
        vendors=vendor_names,
    )
    requirement_ids = {
        item.tag.casefold().strip(): item.id
        for item in revision.requirements
    }
    rows = [
        TechnicalEvaluationRow(
            offer_id=metadata[" ".join(finding.vendor.casefold().split())].id,
            technical_revision=metadata[" ".join(finding.vendor.casefold().split())].technical_revision,
            rfq_revision_id=revision.id,
            requirement_id=requirement_ids[finding.requirement.casefold().strip()],
            rfq_revision=revision.revision,
            requirement=finding.requirement,
            vendor=finding.vendor,
            parameter=finding.parameter,
            required=finding.required,
            offered=finding.offered,
            status=finding.status,
            gap_type=finding.gap_type,
            evidence=finding.evidence,
            claim_status=finding.claim_status,
        )
        for finding in findings
    ]
    return TechnicalEvaluationResponse(
        package_id=package.id,
        rfq_revision_id=revision.id,
        rfq_revision=revision.revision,
        rows=rows,
    )


@app.get("/packages/{package_id}/technical-evaluation", response_model=TechnicalEvaluationResponse)
def technical_evaluation(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> TechnicalEvaluationResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    return _technical_evaluation_rows(package, db)


@app.get("/packages/{package_id}/comparison", response_model=ComparisonResponse)
def compare_package(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> ComparisonResponse:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    rows = [
        ComparisonRow(
            vendor=str(row["vendor"]),
            parameter=str(row["parameter"]),
            required=str(row["required"]),
            offered=None if row["offered"] is None else str(row["offered"]),
            status=str(row["status"]),
        )
        for row in _technical_comparison_rows(package)
    ]
    return ComparisonResponse(
        package_id=package.id,
        technical_locked=package.technical_bid_locked,
        commercial_open=package.commercial_evaluation_open,
        rows=rows,
    )


@app.get("/packages/{package_id}/decision-support", response_model=DecisionSupportResponse)
def package_decision_support(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> DecisionSupportResponse:
    """Return deterministic, auditable technical decision support."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    active_offers = _active_vendor_offers(package)
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    requirement_types = {
        item.tag: item.requirement_type
        for item in revision.requirements
    }
    vendor_values = [
        VendorValue(
            offer.vendor_name,
            claim.parameter,
            claim.value,
            claim.evidence,
            _claim_status(claim.claim_status),
        )
        for offer in active_offers
        for claim in offer.claims
    ]
    result = build_decision_support(
        requirements,
        vendor_values,
        vendors=[offer.vendor_name for offer in active_offers],
        requirement_types=requirement_types,
    )
    return DecisionSupportResponse(
        package_id=package.id,
        requirements_checked=len(requirements),
        vendors_checked=len(active_offers),
        vendors=[DecisionSupportVendorRead.model_validate(item) for item in result["vendors"]],
        rows=[DecisionSupportRowRead.model_validate(item) for item in result["rows"]],
        formula=result["formula"],
    )


def _get_evaluation_settings(db: Session, package: ProcurementPackage) -> PackageEvaluationSettings:
    settings = db.scalar(
        select(PackageEvaluationSettings).where(
            PackageEvaluationSettings.package_id == package.id
        )
    )
    if settings is None:
        settings = PackageEvaluationSettings(
            package_id=package.id,
            technical_weight=70.0,
            commercial_weight=30.0,
        )
        db.add(settings)
        db.flush()
    return settings


@app.get("/packages/{package_id}/evaluation-weighting", response_model=EvaluationWeightingRead)
def get_evaluation_weighting(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationWeightingRead:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    settings = _get_evaluation_settings(db, package)
    db.commit()
    return EvaluationWeightingRead(
        package_id=package.id,
        technical_weight=settings.technical_weight,
        commercial_weight=settings.commercial_weight,
        locked=package.commercial_evaluation_open,
    )


@app.put("/packages/{package_id}/evaluation-weighting", response_model=EvaluationWeightingRead)
def update_evaluation_weighting(
    package_id: int,
    payload: EvaluationWeightingUpdate,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EvaluationWeightingRead:
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")
    if package.commercial_evaluation_open:
        raise HTTPException(status_code=409, detail="evaluation weighting is locked after commercial opening")
    if abs((payload.technical_weight + payload.commercial_weight) - 100.0) > 1e-9:
        raise HTTPException(status_code=422, detail="technical and commercial weights must total 100%")
    settings = _get_evaluation_settings(db, package)
    old = f"{settings.technical_weight:.2f}/{settings.commercial_weight:.2f}"
    settings.technical_weight = payload.technical_weight
    settings.commercial_weight = payload.commercial_weight
    settings.updated_at = datetime.now(UTC)
    _audit(
        db,
        package,
        user,
        "EVALUATION_WEIGHTING_CHANGED",
        from_status=old,
        to_status=f"{payload.technical_weight:.2f}/{payload.commercial_weight:.2f}",
    )
    db.commit()
    db.refresh(settings)
    return EvaluationWeightingRead(
        package_id=package.id,
        technical_weight=settings.technical_weight,
        commercial_weight=settings.commercial_weight,
        locked=False,
    )


@app.get("/packages/{package_id}/integrated-evaluation", response_model=IntegratedEvaluationResponse)
def package_integrated_evaluation(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> IntegratedEvaluationResponse:
    """Return deterministic technical-commercial evaluation for human review."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")

    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    active_offers = _active_vendor_offers(package)
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    requirement_types = {item.tag: item.requirement_type for item in revision.requirements}
    vendor_values = [
        VendorValue(
            offer.vendor_name,
            claim.parameter,
            claim.value,
            claim.evidence,
            _claim_status(claim.claim_status),
        )
        for offer in active_offers
        for claim in offer.claims
    ]
    technical = build_decision_support(
        requirements,
        vendor_values,
        vendors=[offer.vendor_name for offer in active_offers],
        requirement_types=requirement_types,
    )
    commercial_values = [
        CommercialValue(
            offer.vendor_name,
            offer.price or "",
            offer.currency or "",
            offer.lead_time or "",
            offer.warranty or "",
            "",
            "",
            "UNVERIFIED",
        )
        for offer in active_offers
    ]
    commercial_rows = build_commercial_risk_review(commercial_values)
    settings = _get_evaluation_settings(db, package)
    evaluation = build_integrated_evaluation(
        technical["vendors"],
        commercial_rows,
        technical_weight=settings.technical_weight,
        commercial_weight=settings.commercial_weight,
    )
    return IntegratedEvaluationResponse(
        package_id=package.id,
        status=evaluation["status"],
        formula=evaluation["formula"],
        decision_note=evaluation["decision_note"],
        vendor_profiles=[
            IntegratedVendorEvaluationRead.model_validate(item)
            for item in evaluation["vendor_profiles"]
        ],
        review_actions=evaluation["review_actions"],
    )


@app.get("/packages/{package_id}/engineering-decision-summary", response_model=EngineeringDecisionSummaryRead)
def package_engineering_decision_summary(
    package_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> EngineeringDecisionSummaryRead:
    """Return an auditable technical disposition without selecting a supplier."""
    package = db.get(ProcurementPackage, package_id)
    if package is None or not is_member(db, user.id, package.project.organization_id):
        raise HTTPException(status_code=404, detail="package not found")

    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    active_offers = _active_vendor_offers(package)
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    requirement_types = {
        item.tag: item.requirement_type
        for item in revision.requirements
    }
    vendor_values = [
        VendorValue(
            offer.vendor_name,
            claim.parameter,
            claim.value,
            claim.evidence,
            _claim_status(claim.claim_status),
        )
        for offer in active_offers
        for claim in offer.claims
    ]
    result = build_decision_support(
        requirements,
        vendor_values,
        vendors=[offer.vendor_name for offer in active_offers],
        requirement_types=requirement_types,
    )
    summary = (
        build_engineering_decision_summary(result["vendors"])
        if active_offers
        else {
            "status": "INSUFFICIENT_VENDOR_DATA",
            "decision_basis": ["No vendor offers are available for engineering review."],
            "vendor_profiles": [],
            "review_actions": ["Obtain at least one vendor quotation before technical disposition."],
        }
    )
    return EngineeringDecisionSummaryRead(
        package_id=package.id,
        status=summary["status"],
        decision_basis=summary["decision_basis"],
        vendor_profiles=[
            EngineeringVendorProfileRead.model_validate(item)
            for item in summary["vendor_profiles"]
        ],
        review_actions=summary["review_actions"],
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
    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    active_offers = _active_vendor_offers(package)
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    claims: list[tuple[VendorOffer, VendorClaim]] = []
    vendor_values: list[VendorValue] = []
    for offer in active_offers:
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

    revision_id = package.current_rfq_revision_id
    if revision_id is None:
        raise HTTPException(status_code=409, detail="current RFQ revision is not initialized")
    revision = db.get(RfqRevision, revision_id)
    if revision is None or revision.package_id != package.id:
        raise HTTPException(status_code=409, detail="current RFQ revision is not available")
    active_offers = _active_vendor_offers(package)
    requirements = [
        EngineRequirement(item.tag, item.parameter, item.required_value)
        for item in revision.requirements
    ]
    vendor_values: list[VendorValue] = []
    for offer in active_offers:
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
        for offer in active_offers
        if any(
            value
            for value in (offer.price, offer.currency, offer.lead_time, offer.warranty, offer.source_text)
        )
    ]
    report = build_report(requirements, vendor_values, commercial_values)
    decision_support = build_decision_support(
        requirements,
        vendor_values,
        vendors=[offer.vendor_name for offer in active_offers],
        requirement_types={item.tag: item.requirement_type for item in revision.requirements},
    )
    report["decision_support"] = decision_support
    commercial_values = [
        CommercialValue(
            offer.vendor_name,
            offer.price or "",
            offer.currency or "",
            offer.lead_time or "",
            offer.warranty or "",
            "",
            "",
            "UNVERIFIED",
        )
        for offer in active_offers
    ]
    commercial_rows = build_commercial_risk_review(commercial_values)
    settings = _get_evaluation_settings(db, package)
    report["integrated_evaluation"] = build_integrated_evaluation(
        decision_support["vendors"],
        commercial_rows,
        technical_weight=settings.technical_weight,
        commercial_weight=settings.commercial_weight,
    )
    report["engineering_decision_summary"] = (
        build_engineering_decision_summary(decision_support["vendors"])
        if active_offers
        else {
            "status": "INSUFFICIENT_VENDOR_DATA",
            "decision_basis": ["No vendor offers are available for engineering review."],
            "vendor_profiles": [],
            "review_actions": ["Obtain at least one vendor quotation before technical disposition."],
        }
    )
    return report


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