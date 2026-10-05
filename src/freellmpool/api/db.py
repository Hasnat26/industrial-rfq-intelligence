"""Small SQLAlchemy persistence layer for the procurement SaaS MVP."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def _database_url() -> str:
    return os.getenv("INDUSTRIAL_RFQ_DATABASE_URL", "sqlite:///./industrial_rfq.db")


SESSION_TTL_HOURS = 24


DATABASE_URL = _database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    projects: Mapped[list[Project]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    """A registered account. Passwords are stored only as salted hashes."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OrganizationMembership(Base):
    """The tenant boundary: which user belongs to which organization, and in what role."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_memberships_org_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class AuthSession(Base):
    """Opaque bearer tokens; only the SHA-256 digest of a token is persisted."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="sessions")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    organization: Mapped[Organization] = relationship(back_populates="projects")
    packages: Mapped[list[ProcurementPackage]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProcurementPackage(Base):
    __tablename__ = "procurement_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(250))
    category: Mapped[str] = mapped_column(String(100), index=True)
    mode: Mapped[str] = mapped_column(String(30))
    technical_bid_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    commercial_evaluation_open: Mapped[bool] = mapped_column(Boolean, default=False)
    project: Mapped[Project] = relationship(back_populates="packages")
    requirements: Mapped[list[Requirement]] = relationship(back_populates="package", cascade="all, delete-orphan")
    offers: Mapped[list[VendorOffer]] = relationship(back_populates="package", cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    tag: Mapped[str] = mapped_column(String(100))
    parameter: Mapped[str] = mapped_column(String(200))
    required_value: Mapped[str] = mapped_column(String(250))
    requirement_type: Mapped[str] = mapped_column(String(30), default="MANDATORY")
    acceptance_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    package: Mapped[ProcurementPackage] = relationship(back_populates="requirements")


class VendorClaim(Base):
    __tablename__ = "vendor_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("vendor_offers.id"), index=True)
    parameter: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(String(250))
    evidence: Mapped[str] = mapped_column(Text, default="")
    claim_status: Mapped[str] = mapped_column(String(40), default="UNVERIFIED")
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendor_documents.id"), nullable=True, index=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_table: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    offer: Mapped[VendorOffer] = relationship(back_populates="claims")
    source_document: Mapped[VendorDocument | None] = relationship()


class VendorOffer(Base):
    __tablename__ = "vendor_offers"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "vendor_key",
            "technical_revision",
            name="uq_vendor_offers_package_vendor_revision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    parent_offer_id: Mapped[int | None] = mapped_column(ForeignKey("vendor_offers.id"), nullable=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    part_number: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    vendor_key: Mapped[str] = mapped_column(String(200), default="")
    technical_revision: Mapped[str] = mapped_column(String(50), default="R1")
    technical_status: Mapped[str] = mapped_column(String(40), default="PENDING")
    commercial_status: Mapped[str] = mapped_column(String(30), default="LOCKED")
    price: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    lead_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    package: Mapped[ProcurementPackage] = relationship(back_populates="offers")
    parent_offer: Mapped[VendorOffer | None] = relationship(
        remote_side="VendorOffer.id", back_populates="revisions"
    )
    revisions: Mapped[list[VendorOffer]] = relationship(back_populates="parent_offer")
    claims: Mapped[list[VendorClaim]] = relationship(back_populates="offer", cascade="all, delete-orphan")
    deviations: Mapped[list[TechnicalDeviation]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )
    clarifications: Mapped[list[TechnicalClarification]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )
    documents: Mapped[list[VendorDocument]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )


def _auto_create_allowed() -> bool:
    """Development SQLite databases self-bootstrap; production opt-in only."""
    flag = os.getenv("INDUSTRIAL_RFQ_AUTO_CREATE_TABLES")
    if flag == "1":
        return True
    if flag == "0":
        return False
    return DATABASE_URL.startswith("sqlite")


def init_db() -> None:
    """Create any missing tables without dropping or altering existing ones.

    Schema changes must be delivered through Alembic migrations
    (`alembic upgrade head`). Application startup never recreates or drops
    tables on non-SQLite databases unless INDUSTRIAL_RFQ_AUTO_CREATE_TABLES=1.
    """
    if _auto_create_allowed():
        Base.metadata.create_all(bind=engine, checkfirst=True)


def get_db() -> Generator[object, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LifecycleEvent(Base):
    """Canonical post-procurement event linked to a package and optional offer."""

    __tablename__ = "lifecycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("vendor_offers.id"), nullable=True, index=True)
    asset_id: Mapped[str] = mapped_column(String(200), index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    package: Mapped[ProcurementPackage] = relationship()
    offer: Mapped[VendorOffer | None] = relationship()
    created_by: Mapped[User] = relationship()


class ProcurementDecision(Base):
    __tablename__ = "procurement_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), unique=True, index=True)
    selected_offer_id: Mapped[int] = mapped_column(ForeignKey("vendor_offers.id"), index=True)
    decision_status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    rationale: Mapped[str] = mapped_column(Text)
    decided_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    package: Mapped[ProcurementPackage] = relationship()
    selected_offer: Mapped[VendorOffer] = relationship()
    decided_by: Mapped[User] = relationship()


class ProcurementAuditEvent(Base):
    __tablename__ = "procurement_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("vendor_offers.id"), nullable=True, index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    from_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    package: Mapped[ProcurementPackage] = relationship()
    offer: Mapped[VendorOffer | None] = relationship()
    actor: Mapped[User] = relationship()


class TechnicalDeviation(Base):
    __tablename__ = "technical_deviations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("vendor_offers.id"), index=True)
    parameter: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(30), default="MINOR")
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer: Mapped[VendorOffer] = relationship(back_populates="deviations")


class TechnicalClarification(Base):
    __tablename__ = "technical_clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("vendor_offers.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer: Mapped[VendorOffer] = relationship(back_populates="clarifications")


class VendorDocument(Base):
    __tablename__ = "vendor_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("vendor_offers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    document_type: Mapped[str] = mapped_column(String(30), default="VENDOR_OFFER")
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    offer: Mapped[VendorOffer] = relationship(back_populates="documents")
    pages: Mapped[list[VendorDocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class VendorDocumentPage(Base):
    __tablename__ = "vendor_document_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("vendor_documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    document: Mapped[VendorDocument] = relationship(back_populates="pages")
