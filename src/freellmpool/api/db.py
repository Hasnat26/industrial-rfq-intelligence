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
    vendor_name: Mapped[str] = mapped_column(String(200))
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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[object, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
