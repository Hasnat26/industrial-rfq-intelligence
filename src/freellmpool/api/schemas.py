"""Pydantic API contracts for the procurement SaaS MVP."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class UserRead(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class OrganizationMembershipRead(BaseModel):
    organization_id: int
    name: str
    role: str


class CurrentUserRead(BaseModel):
    id: int
    email: str
    organizations: list[OrganizationMembershipRead]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationRead(OrganizationCreate):
    id: int

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=100)


class ProjectRead(ProjectCreate):
    id: int

    model_config = {"from_attributes": True}


class RequirementCreate(BaseModel):
    tag: str = Field(min_length=1, max_length=100)
    parameter: str = Field(min_length=1, max_length=200)
    required_value: str = Field(min_length=1, max_length=250)
    requirement_type: str = "MANDATORY"
    acceptance_rule: str | None = Field(default=None, max_length=500)


class OfferCreate(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=200)
    technical_revision: str = Field(default="R1", min_length=1, max_length=50)
    price: str | None = None
    currency: str | None = None
    lead_time: str | None = None
    warranty: str | None = None
    source_text: str | None = None


class PackageCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=250)
    category: str = Field(min_length=1, max_length=100)
    mode: str = "STANDARD"
    requirements: list[RequirementCreate] = Field(default_factory=list)


class PackageRead(BaseModel):
    id: int
    project_id: int
    name: str
    category: str
    mode: str
    technical_bid_locked: bool
    commercial_evaluation_open: bool

    model_config = {"from_attributes": True}


class PackageWorkflowResponse(BaseModel):
    package_id: int
    mode: str
    technical_bid_locked: bool
    commercial_evaluation_open: bool
    offer_count: int
    technical_status_counts: dict[str, int]
    open_deviation_count: int
    open_clarification_count: int


class TechnicalStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=40)


class OfferRevisionCreate(BaseModel):
    technical_revision: str = Field(min_length=1, max_length=50)
    source_text: str | None = None


class CommercialStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=30)


class CommercialComparisonRow(BaseModel):
    offer_id: int
    vendor: str
    technical_revision: str
    technical_status: str
    commercial_status: str
    price: str | None
    currency: str | None
    lead_time: str | None
    warranty: str | None


class CommercialComparisonResponse(BaseModel):
    package_id: int
    commercial_open: bool
    rows: list[CommercialComparisonRow]


class OfferRead(BaseModel):
    id: int
    package_id: int
    parent_offer_id: int | None
    vendor_name: str
    technical_revision: str
    technical_status: str
    commercial_status: str
    price: str | None
    currency: str | None
    lead_time: str | None
    warranty: str | None

    model_config = {"from_attributes": True}


class ComparisonRow(BaseModel):
    vendor: str
    parameter: str
    required: str
    offered: str | None
    status: str


class ComparisonResponse(BaseModel):
    package_id: int
    technical_locked: bool
    commercial_open: bool
    rows: list[ComparisonRow]


class ClaimCreate(BaseModel):
    parameter: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=250)
    evidence: str = ""
    claim_status: str = "UNVERIFIED"
    source_document_id: int | None = Field(default=None, ge=1)
    source_page: int | None = Field(default=None, ge=1)
    source_section: str | None = Field(default=None, max_length=200)
    source_table: str | None = Field(default=None, max_length=100)
    source_cell: str | None = Field(default=None, max_length=100)


class TechnicalDeviationCreate(BaseModel):
    parameter: str = Field(min_length=1, max_length=200)
    severity: str = Field(default="MINOR", min_length=1, max_length=30)
    description: str = Field(min_length=1)
    status: str = Field(default="OPEN", min_length=1, max_length=30)
    resolution: str | None = None


class IssueResolution(BaseModel):
    note: str = Field(min_length=1)


class TechnicalDeviationRead(TechnicalDeviationCreate):
    id: int
    offer_id: int

    model_config = {"from_attributes": True}


class TechnicalClarificationCreate(BaseModel):
    question: str = Field(min_length=1)
    response: str | None = None
    status: str = Field(default="OPEN", min_length=1, max_length=30)


class TechnicalClarificationRead(TechnicalClarificationCreate):
    id: int
    offer_id: int
    resolution: str | None = None

    model_config = {"from_attributes": True}


class ClaimRead(ClaimCreate):
    id: int
    offer_id: int

    model_config = {"from_attributes": True}


class RfqResponse(BaseModel):
    package_id: int
    title: str
    mode: str
    category: str
    requirements: list[RequirementCreate]
    instructions: list[str]


class VendorDocumentPageRead(BaseModel):
    page_number: int
    text: str

    model_config = {"from_attributes": True}


class VendorDocumentRead(BaseModel):
    id: int
    offer_id: int
    filename: str
    content_type: str | None
    document_type: str
    page_count: int
    pages: list[VendorDocumentPageRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class EvidenceRow(BaseModel):
    claim_id: int
    offer_id: int
    vendor: str
    technical_revision: str
    field: str
    value: str
    evidence: str
    claim_status: str
    review_required: str
    source: str
    page: int | None
    section: str
    table: str
    cell: str
    source_document_id: int | None
    source_document_filename: str | None


class EvidenceResponse(BaseModel):
    package_id: int
    rows: list[EvidenceRow]


class QuotationBatchEntry(BaseModel):
    """One vendor quotation inside a batch ingestion request."""

    vendor_name: str = Field(min_length=1, max_length=200)
    technical_revision: str = Field(default="R1", min_length=1, max_length=50)
    price: str | None = None
    currency: str | None = None
    lead_time: str | None = None
    warranty: str | None = None
    source_text: str | None = None


class QuotationBatchResponse(BaseModel):
    """Atomically ingested quotations and their extracted documents."""

    package_id: int
    offers: list[OfferRead]
    document_ids: list[int]


class ProductCategoryParameterRead(BaseModel):
    key: str
    label: str
    mandatory: bool
    unit: str | None


class ProductCategoryRead(BaseModel):
    key: str
    name: str
    description: str
    parameters: list[ProductCategoryParameterRead]
