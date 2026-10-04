"""Pydantic API contracts for the procurement SaaS MVP."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class TechnicalStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=40)


class OfferRead(BaseModel):
    id: int
    package_id: int
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


class TechnicalDeviationCreate(BaseModel):
    parameter: str = Field(min_length=1, max_length=200)
    severity: str = Field(default="MINOR", min_length=1, max_length=30)
    description: str = Field(min_length=1)
    status: str = Field(default="OPEN", min_length=1, max_length=30)
    resolution: str | None = None


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

    model_config = {"from_attributes": True}


class ClaimRead(ClaimCreate):
    id: int

    model_config = {"from_attributes": True}


class RfqResponse(BaseModel):
    package_id: int
    title: str
    mode: str
    category: str
    requirements: list[RequirementCreate]
    instructions: list[str]

