"""Industrial RFQ intelligence workflows for the industrial-rfq-intelligence package.

The first vertical slice is a deterministic RFQ compliance reviewer.  It is
deliberately dependency-free and can be used as a stable foundation for a
future LLM-assisted extraction layer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

RFQ_SCHEMA_VERSION = "1.0"
SUPPORTED_RFQ_SCHEMA_VERSIONS = frozenset({RFQ_SCHEMA_VERSION})

ClaimStatus = Literal[
    "VERIFIED",
    "PARTIALLY VERIFIED",
    "UNVERIFIED",
    "INFERENCE",
    "ASSUMPTION",
    "CONTRADICTED",
]


@dataclass(frozen=True)
class EvidenceProvenance:
    """Normalized source location for an extracted claim."""

    source: str
    page: int | None = None
    section: str | None = None
    table: str | None = None
    cell: str | None = None


@dataclass(frozen=True)
class Requirement:
    tag: str
    parameter: str
    required: str


@dataclass(frozen=True)
class VendorValue:
    vendor: str
    parameter: str
    value: str
    evidence: str
    claim_status: ClaimStatus = "UNVERIFIED"
    provenance: EvidenceProvenance | None = None


@dataclass(frozen=True)
class CommercialValue:
    vendor: str
    price: str
    currency: str
    lead_time: str
    warranty: str
    payment_terms: str
    evidence: str
    claim_status: ClaimStatus = "UNVERIFIED"
    provenance: EvidenceProvenance | None = None


DEFAULT_REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement("R-01", "Rated voltage", "415 V"),
    Requirement("R-02", "Motor power", "75 kW"),
    Requirement("R-03", "Efficiency class", "IE3"),
    Requirement("R-04", "Ingress protection", "IP55"),
)

DEFAULT_VENDOR_DATA: tuple[VendorValue, ...] = (
    VendorValue("Vendor A", "Rated voltage", "415 V", "Quotation p.1", "VERIFIED"),
    VendorValue("Vendor A", "Motor power", "75 kW", "Quotation p.1", "VERIFIED"),
    VendorValue("Vendor A", "Efficiency class", "IE3", "Quotation p.2", "VERIFIED"),
    VendorValue("Vendor A", "Ingress protection", "IP55", "Quotation p.2", "VERIFIED"),
    VendorValue("Vendor B", "Rated voltage", "415 V", "Quotation p.1", "VERIFIED"),
    VendorValue("Vendor B", "Motor power", "75 kW", "Quotation p.1", "VERIFIED"),
    VendorValue("Vendor B", "Efficiency class", "IE2", "Quotation p.2", "VERIFIED"),
    VendorValue("Vendor B", "Ingress protection", "IP55", "Quotation p.2", "VERIFIED"),
)


def _normalise_requirements(
    requirements: Sequence[Requirement] | None,
) -> tuple[Requirement, ...]:
    return tuple(requirements or DEFAULT_REQUIREMENTS)


def _normalise_vendor_data(
    vendor_data: Sequence[VendorValue] | None,
) -> tuple[VendorValue, ...]:
    return tuple(DEFAULT_VENDOR_DATA if vendor_data is None else vendor_data)


def _parse_provenance(item: dict[str, object], location: str) -> EvidenceProvenance | None:
    raw = item.get("provenance")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{location}.provenance must be an object when provided")
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"{location}.provenance.source must be a non-empty string")
    page = raw.get("page")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page < 1):
        raise ValueError(f"{location}.provenance.page must be a positive integer or null")
    page_value: int | None = page if isinstance(page, int) and not isinstance(page, bool) else None
    fields: dict[str, str | None] = {}
    for field in ("section", "table", "cell"):
        value = raw.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{location}.provenance.{field} must be a string or null")
        fields[field] = value.strip() if isinstance(value, str) else None
    return EvidenceProvenance(
        source=source.strip(),
        page=page_value,
        section=fields["section"],
        table=fields["table"],
        cell=fields["cell"],
    )


def load_rfq_input(path: str | Path) -> tuple[list[Requirement], list[VendorValue], list[CommercialValue]]:
    """Load and strictly validate a versioned structured RFQ JSON input file."""
    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read RFQ input '{input_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid RFQ JSON in '{input_path}': {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("RFQ input must be a JSON object")
    schema_version = payload.get("schema_version", RFQ_SCHEMA_VERSION)
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("RFQ input 'schema_version' must be a non-empty string")
    schema_version = schema_version.strip()
    if schema_version not in SUPPORTED_RFQ_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported RFQ schema_version: {schema_version!r}; supported: {sorted(SUPPORTED_RFQ_SCHEMA_VERSIONS)}")
    raw_requirements = payload.get("requirements")
    raw_vendor_data = payload.get("vendor_data")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise ValueError("RFQ input requires a non-empty 'requirements' array")
    if not isinstance(raw_vendor_data, list) or not raw_vendor_data:
        raise ValueError("RFQ input requires a non-empty 'vendor_data' array")
    def _required_text(item: dict[str, object], field: str, location: str) -> str:
        if field not in item:
            raise ValueError(f"{location} missing field: {field}")
        value = item[field]
        if not isinstance(value, str):
            raise ValueError(f"{location} fields must be strings; each field must be a string")
        value = value.strip()
        if not value:
            raise ValueError(f"{location}.{field} must not be empty")
        return value
    def _optional_text(item: dict[str, object], field: str, location: str) -> str:
        value = item.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"{location}.{field} must be a string when provided")
        return value.strip()
    requirements: list[Requirement] = []
    requirement_tags: set[str] = set()
    for index, item in enumerate(raw_requirements):
        location = f"requirements[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        tag = _required_text(item, "tag", location)
        parameter = _required_text(item, "parameter", location)
        required = _required_text(item, "required", location)
        tag_key = tag.casefold()
        if tag_key in requirement_tags:
            raise ValueError(f"{location} duplicate tag (duplicate requirement tag): {tag!r}")
        requirement_tags.add(tag_key)
        requirements.append(Requirement(tag, parameter, required))
    allowed_statuses = {"VERIFIED", "PARTIALLY VERIFIED", "UNVERIFIED", "INFERENCE", "ASSUMPTION", "CONTRADICTED"}
    vendor_data: list[VendorValue] = []
    exact_vendor_claims: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(raw_vendor_data):
        location = f"vendor_data[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        vendor = _required_text(item, "vendor", location)
        parameter = _required_text(item, "parameter", location)
        value = _required_text(item, "value", location)
        evidence = _optional_text(item, "evidence", location)
        provenance = _parse_provenance(item, location)
        raw_status = item.get("claim_status", "UNVERIFIED")
        if not isinstance(raw_status, str):
            raise ValueError(f"{location}.claim_status must be a string")
        claim_status = raw_status.strip().upper()
        if not evidence:
            claim_status = "UNVERIFIED"
        if claim_status not in allowed_statuses:
            raise ValueError(f"{location} invalid claim_status: {claim_status!r}")
        duplicate_key = (vendor.casefold(), _normalise_parameter(parameter), _normalise_value(value), evidence.casefold())
        if duplicate_key in exact_vendor_claims:
            raise ValueError(f"{location} duplicates an existing vendor claim")
        exact_vendor_claims.add(duplicate_key)
        vendor_data.append(VendorValue(vendor, parameter, value, evidence, cast(ClaimStatus, claim_status), provenance))
    raw_commercial = payload.get("commercial_data", [])
    if not isinstance(raw_commercial, list):
        raise ValueError("RFQ input 'commercial_data' must be an array when provided")
    commercial_data: list[CommercialValue] = []
    commercial_fields = ("vendor", "price", "currency", "lead_time", "warranty", "payment_terms")
    commercial_vendors: set[str] = set()
    for index, item in enumerate(raw_commercial):
        location = f"commercial_data[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        values = {field: _required_text(item, field, location) for field in commercial_fields}
        vendor_key = values["vendor"].casefold()
        if vendor_key in commercial_vendors:
            raise ValueError(f"{location} duplicates commercial data for vendor {values['vendor']!r}")
        commercial_vendors.add(vendor_key)
        evidence = _optional_text(item, "evidence", location)
        provenance = _parse_provenance(item, location)
        raw_status = item.get("claim_status", "UNVERIFIED")
        if not isinstance(raw_status, str):
            raise ValueError(f"{location}.claim_status must be a string")
        claim_status = raw_status.strip().upper()
        if not evidence:
            claim_status = "UNVERIFIED"
        if claim_status == "VERIFIED" and provenance is None:
            raise ValueError(f"{location} VERIFIED claims require provenance")
        if claim_status not in allowed_statuses:
            raise ValueError(f"{location} invalid claim_status: {claim_status!r}")
        commercial_data.append(CommercialValue(**values, evidence=evidence, claim_status=cast(ClaimStatus, claim_status), provenance=provenance))
    return requirements, vendor_data, commercial_data


@dataclass(frozen=True)
class DocumentPage:
    source: str
    page: int
    text: str


def extract_document_pages(path: str | Path) -> list[DocumentPage]:
    """Extract text while preserving source and page provenance."""
    document = Path(path)
    if not document.is_file():
        raise ValueError(f"document not found: {document}")
    suffix = document.suffix.casefold()
    if suffix in {".txt", ".md"}:
        text = document.read_text(encoding="utf-8")
        return [DocumentPage(str(document), 1, text)]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF ingestion requires the pypdf dependency") from exc
        try:
            reader = PdfReader(str(document))
        except Exception as exc:
            raise ValueError(f"cannot read PDF: {document}") from exc
        pages: list[DocumentPage] = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(DocumentPage(str(document), number, text))
        if not pages:
            raise ValueError(f"PDF contains no pages: {document}")
        return pages
    raise ValueError("unsupported document type; expected .txt, .md, or .pdf")


def extract_document_pages_with_ocr(
    path: str | Path,
    *,
    language: str = "eng",
    min_text_chars: int = 20,
) -> list[DocumentPage]:
    """Extract PDF text and OCR pages that contain little or no machine text.

    OCR is optional so the deterministic core remains dependency-light. Install
    the package 'ocr' extra and the Tesseract executable to enable scanned-PDF OCR.
    Pages retain the same source/page provenance as native PDF extraction.
    """
    document = Path(path)
    pages = extract_document_pages(document)
    if document.suffix.casefold() != ".pdf":
        return pages
    if min_text_chars < 0:
        raise ValueError("min_text_chars must be non-negative")
    try:
        import importlib

        fitz = importlib.import_module("fitz")
        pytesseract = importlib.import_module("pytesseract")
        image_module = importlib.import_module("PIL.Image")
    except ImportError as exc:
        raise ValueError(
            "PDF OCR requires the 'ocr' optional dependencies; install with: "
            "pip install 'industrial-rfq-intelligence[ocr]'"
        ) from exc
    try:
        pdf = fitz.open(str(document))
    except Exception as exc:
        raise ValueError(f"cannot open PDF for OCR: {document}") from exc
    ocr_pages: list[DocumentPage] = []
    try:
        for index, page in enumerate(pdf, start=1):
            native_text = pages[index - 1].text if index <= len(pages) else ""
            if len(native_text.strip()) >= min_text_chars:
                ocr_pages.append(DocumentPage(str(document), index, native_text))
                continue
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = image_module.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            try:
                text = pytesseract.image_to_string(image, lang=language)
            except Exception as exc:
                raise ValueError(f"OCR failed on {document}, page {index}: {exc}") from exc
            ocr_pages.append(DocumentPage(str(document), index, text))
    finally:
        pdf.close()
    return ocr_pages

def document_text(pages: Sequence[DocumentPage]) -> str:
    """Build LLM-ready text with explicit source/page markers."""
    return "\n\n".join(
        f"[SOURCE: {page.source} | PAGE: {page.page}]\n{page.text.strip()}"
        for page in pages
        if page.text.strip()
    )

@dataclass(frozen=True)
class ExtractedClaimCandidate:
    """Deterministic quotation-field extraction with page-level provenance."""

    parameter: str
    value: str
    evidence: str
    page: int
    section: str | None = None
    table: str | None = None
    cell: str | None = None


def extract_claim_candidates(
    pages: Sequence[DocumentPage],
    requirements: Sequence[Requirement],
) -> list[ExtractedClaimCandidate]:
    """Extract explicit ``parameter: value`` style quotation fields.

    This is intentionally conservative: only a requirement parameter (or one
    of its configured aliases) may become a claim. No compliance judgment is
    made here; ``build_matrix`` remains the deterministic decision layer.
    """
    import re

    canonical_by_alias: dict[str, str] = {}
    for requirement in requirements:
        canonical = _normalise_parameter(requirement.parameter)
        canonical_by_alias[canonical] = requirement.parameter
        for alias, target in _PARAMETER_ALIASES.items():
            if target == canonical:
                canonical_by_alias[_normalise_parameter(alias)] = requirement.parameter

    candidates: list[ExtractedClaimCandidate] = []
    field_pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?P<label>[^:=|\t]{2,100}?)\s*"
        r"(?::|=|\||\t)\s*(?P<value>[^|]+?)\s*(?:\|.*)?$",
        flags=re.IGNORECASE,
    )

    for page in pages:
        section: str | None = None
        for raw_line in page.text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            heading = re.match(r"^#{1,6}\s+(.+)$", line)
            if heading:
                section = heading.group(1).strip()[:200]
                continue
            match = field_pattern.match(line)
            if match is None:
                continue
            label = " ".join(match.group("label").split())
            value = " ".join(match.group("value").split()).strip(" ;")
            parameter = canonical_by_alias.get(_normalise_parameter(label))
            if parameter is None or not value:
                continue
            candidates.append(
                ExtractedClaimCandidate(
                    parameter=parameter,
                    value=value,
                    evidence=f"{page.source}, page {page.page}: {line}",
                    page=page.page,
                    section=section,
                )
            )
    return candidates


_PARAMETER_ALIASES = {
    "rated voltage": "rated voltage",
    "voltage": "rated voltage",
    "nominal voltage": "rated voltage",
    "motor voltage": "rated voltage",
    "motor power": "motor power",
    "rated power": "motor power",
    "power": "motor power",
    "current": "rated current",
    "rated current": "rated current",
    "motor current": "rated current",
    "frequency": "frequency",
    "rated frequency": "frequency",
    "speed": "rotational speed",
    "rated speed": "rotational speed",
    "rotational speed": "rotational speed",
    "rpm": "rotational speed",
    "torque": "rated torque",
    "rated torque": "rated torque",
    "temperature": "temperature",
    "ambient temperature": "temperature",
    "operating temperature": "temperature",
    "pressure": "pressure",
    "operating pressure": "pressure",
    "length": "length",
    "width": "length",
    "height": "length",
    "diameter": "length",
    "mass": "mass",
    "weight": "mass",
    "efficiency class": "efficiency class",
    "efficiency": "efficiency class",
    "energy efficiency": "efficiency class",
    "ingress protection": "ingress protection",
    "ip rating": "ingress protection",
    "protection": "ingress protection",
}

def _normalise_parameter(parameter: str) -> str:
    key = " ".join(parameter.casefold().replace("_", " ").replace("-", " ").split())
    return _PARAMETER_ALIASES.get(key, key)

def _normalise_value(value: str) -> str:
    return " ".join(value.casefold().replace(",", "").split())

def _numeric_unit(value: str) -> tuple[float, str] | None:
    import re
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z°/%]+)", value.strip())
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).casefold()
    conversions = {
        # Electrical voltage
        "v": ("v", 1.0), "kv": ("v", 1000.0),
        # Electrical/current
        "a": ("a", 1.0), "ka": ("a", 1000.0),
        # Power
        "w": ("w", 1.0), "kw": ("w", 1000.0), "mw": ("w", 1_000_000.0),
        # Frequency
        "hz": ("hz", 1.0), "khz": ("hz", 1000.0), "mhz": ("hz", 1_000_000.0),
        # Rotational speed
        "rpm": ("rpm", 1.0), "r/min": ("rpm", 1.0),
        # Torque
        "nm": ("nm", 1.0), "knm": ("nm", 1000.0),
        # Temperature
        "c": ("c", 1.0), "°c": ("c", 1.0),
        # Pressure
        "bar": ("pa", 100_000.0), "mbar": ("pa", 100.0),
        "mpa": ("pa", 1_000_000.0), "kpa": ("pa", 1_000.0),
        "pa": ("pa", 1.0),
        # Length
        "mm": ("m", 0.001), "cm": ("m", 0.01), "m": ("m", 1.0),
        "km": ("m", 1000.0),
        # Mass
        "g": ("kg", 0.001), "kg": ("kg", 1.0), "t": ("kg", 1000.0),
    }
    if unit not in conversions:
        return None
    canonical, multiplier = conversions[unit]
    return number * multiplier, canonical

_PARAMETER_DIMENSIONS = {
    "rated voltage": "v",
    "rated current": "a",
    "motor power": "w",
    "frequency": "hz",
    "rotational speed": "rpm",
    "rated torque": "nm",
    "temperature": "c",
    "pressure": "pa",
    "length": "m",
    "mass": "kg",
}


def _engineering_comparison(
    required: str,
    offered: str,
    parameter: str | None = None,
) -> bool | None:
    """Evaluate supported numeric engineering expressions deterministically."""
    import re

    right = _numeric_unit(offered)
    if right is None:
        return None

    expected_dimension = (
        _PARAMETER_DIMENSIONS.get(_normalise_parameter(parameter))
        if parameter
        else None
    )
    if expected_dimension is not None and right[1] != expected_dimension:
        return False

    expression = required.strip().replace("−", "-").replace("–", "-")

    tolerance_match = re.fullmatch(
        r"([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z°]+)\s*(?:±|\+/-)\s*"
        r"(\d+(?:\.\d+)?)\s*%",
        expression,
    )
    if tolerance_match:
        nominal = _numeric_unit(
            f"{tolerance_match.group(1)} {tolerance_match.group(2)}"
        )
        if nominal is None or nominal[1] != right[1]:
            return False
        tolerance = float(tolerance_match.group(3)) / 100.0
        lower = nominal[0] * (1.0 - tolerance)
        upper = nominal[0] * (1.0 + tolerance)
        return lower <= right[0] <= upper

    range_match = re.fullmatch(
        r"([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z°]+)?\s*"
        r"(?:to|-|\.{2})\s*([-+]?\d+(?:\.\d+)?)\s*"
        r"([a-zA-Z°]+)",
        expression,
        flags=re.IGNORECASE,
    )
    if range_match:
        low_unit = range_match.group(2) or range_match.group(4)
        low = _numeric_unit(f"{range_match.group(1)} {low_unit}")
        high = _numeric_unit(
            f"{range_match.group(3)} {range_match.group(4)}"
        )
        if (
            low is None
            or high is None
            or low[1] != high[1]
            or low[1] != right[1]
        ):
            return False
        lower, upper = sorted((low[0], high[0]))
        return lower <= right[0] <= upper

    operator_match = re.fullmatch(
        r"(>=|<=|>|<|=)?\s*([-+]?\d+(?:\.\d+)?)\s*"
        r"([a-zA-Z°]+)",
        expression,
    )
    if operator_match:
        operator = operator_match.group(1) or "="
        target = _numeric_unit(
            f"{operator_match.group(2)} {operator_match.group(3)}"
        )
        if target is None or target[1] != right[1]:
            return False
        if operator == ">=":
            return right[0] >= target[0]
        if operator == "<=":
            return right[0] <= target[0]
        if operator == ">":
            return right[0] > target[0]
        if operator == "<":
            return right[0] < target[0]
        return right[0] == target[0]

    return None

def _values_match(
    required: str,
    offered: str,
    parameter: str | None = None,
) -> bool:
    comparison = _engineering_comparison(required, offered, parameter)
    if comparison is not None:
        return comparison

    left = _numeric_unit(required)
    right = _numeric_unit(offered)
    if left is not None and right is not None and left[1] == right[1]:
        return left[0] == right[0]
    return _normalise_value(required) == _normalise_value(offered)


def _matching_vendor_values(
    values: Sequence[VendorValue],
    vendor: str,
    parameter: str,
) -> list[VendorValue]:
    """Return all claims for a vendor/parameter pair, preserving duplicates."""
    normalised = _normalise_parameter(parameter)
    return [
        value
        for value in values
        if value.vendor == vendor and _normalise_parameter(value.parameter) == normalised
    ]


def _has_conflicting_values(items: Sequence[VendorValue]) -> bool:
    """Detect materially different claims for the same vendor/parameter."""
    if len(items) < 2:
        return False
    first = items[0].value
    return any(
        not _values_match(first, item.value, items[0].parameter)
        for item in items[1:]
    )


def build_matrix(
    requirements: Sequence[Requirement] | None = None,
    vendor_data: Sequence[VendorValue] | None = None,
    vendors: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Build a deterministic vendor-major requirement compliance matrix.

    Rows are ordered Vendor A requirements, then Vendor B requirements, etc.
    Missing evidence is never treated as compliant. Conflicting claims fail closed.
    """
    reqs = _normalise_requirements(requirements)
    values = _normalise_vendor_data(vendor_data)
    vendor_names = [item.vendor for item in values]
    vendor_names.extend(vendor for vendor in (vendors or ()) if vendor.strip())
    vendor_universe = tuple(dict.fromkeys(vendor_names))
    rows: list[dict[str, str]] = []

    for vendor in vendor_universe:
        for req in reqs:
            matches = _matching_vendor_values(values, vendor, req.parameter)
            item = matches[0] if matches else None

            if item is None:
                rows.append({
                    "requirement": req.tag,
                    "vendor": vendor,
                    "parameter": req.parameter,
                    "offered_parameter": "MISSING",
                    "required": req.required,
                    "offered": "MISSING",
                    "status": "UNVERIFIED",
                    "evidence": "No matching quotation field",
                    "claim_status": "UNVERIFIED",
                })
                continue

            if _has_conflicting_values(matches):
                evidence = " | ".join(
                    f"{match.evidence}: {match.value}"
                    for match in matches
                    if match.evidence
                ) or "Conflicting quotation claims"
                rows.append({
                    "requirement": req.tag,
                    "vendor": vendor,
                    "parameter": req.parameter,
                    "offered_parameter": "CONFLICTING",
                    "required": req.required,
                    "offered": "CONFLICTING",
                    "status": "UNVERIFIED",
                    "evidence": evidence,
                    "claim_status": "CONTRADICTED",
                })
                continue

            status = (
                "COMPLIANT"
                if _values_match(req.required, item.value, req.parameter)
                else "DEVIATION"
            )
            if item.claim_status == "CONTRADICTED":
                status = "UNVERIFIED"

            rows.append({
                "requirement": req.tag,
                "vendor": vendor,
                "parameter": req.parameter,
                "offered_parameter": item.parameter,
                "required": req.required,
                "offered": item.value,
                "status": status,
                "evidence": item.evidence,
                "claim_status": item.claim_status,
            })

    return rows


def _provenance_fields(provenance: EvidenceProvenance | None) -> dict[str, str]:
    if provenance is None:
        return {"source": "", "page": "", "section": "", "table": "", "cell": ""}
    return {
        "source": provenance.source,
        "page": "" if provenance.page is None else str(provenance.page),
        "section": provenance.section or "",
        "table": provenance.table or "",
        "cell": provenance.cell or "",
    }


def build_evidence_register(requirements: Sequence[Requirement], vendor_data: Sequence[VendorValue], commercial_data: Sequence[CommercialValue] = ()) -> list[dict[str, str]]:
    """Return a traceable evidence register for every supplied claim."""
    rows: list[dict[str, str]] = []
    for item in vendor_data:
        rows.append({"source_type": "technical_quotation", "vendor": item.vendor, "field": item.parameter, "value": item.value, "evidence": item.evidence, "claim_status": item.claim_status, "review_required": "YES" if item.claim_status != "VERIFIED" else "NO", **_provenance_fields(item.provenance)})
    for entry in commercial_data:
        rows.append({
            "source_type": "commercial_quotation",
            "vendor": entry.vendor,
            "field": "price / lead_time / warranty / payment_terms",
            "value": f"{entry.price} {entry.currency}; {entry.lead_time}; {entry.warranty}; {entry.payment_terms}",
            "evidence": entry.evidence,
            "claim_status": entry.claim_status,
            "review_required": "YES" if entry.claim_status != "VERIFIED" else "NO",
            **_provenance_fields(entry.provenance),
        })
    return rows

_COMMERCIAL_LEAD_TIME_REVIEW_WEEKS = 12.0
_COMMERCIAL_WARRANTY_REVIEW_MONTHS = 12.0


def _normalise_commercial_price(price: str) -> float | None:
    import re

    cleaned = price.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


def _normalise_commercial_lead_time(lead_time: str) -> float | None:
    import re

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(day|days|d|week|weeks|w|month|months|m)",
        lead_time.strip().casefold(),
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit in {"day", "days", "d"}:
        return value / 7.0
    if unit in {"month", "months", "m"}:
        return value * 4.345
    return value


def _normalise_warranty_months(warranty: str) -> float | None:
    import re

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*(month|months|mo|year|years|yr|y)",
        warranty.strip().casefold(),
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    return value * 12.0 if unit in {"year", "years", "yr", "y"} else value


def _commercial_risk_flags(item: CommercialValue) -> list[str]:
    """Return review flags without ranking vendors or selecting a supplier."""
    flags: list[str] = []
    if not item.evidence or item.claim_status != "VERIFIED":
        flags.append("EVIDENCE_REVIEW")
    if _normalise_commercial_price(item.price) is None:
        flags.append("PRICE_FORMAT_REVIEW")
    if not item.currency.strip() or item.currency.strip().upper() != item.currency.strip():
        flags.append("CURRENCY_NORMALIZATION_REVIEW")
    lead_time_weeks = _normalise_commercial_lead_time(item.lead_time)
    if lead_time_weeks is None:
        flags.append("LEAD_TIME_FORMAT_REVIEW")
    elif lead_time_weeks > _COMMERCIAL_LEAD_TIME_REVIEW_WEEKS:
        flags.append("LEAD_TIME_REVIEW")
    warranty_months = _normalise_warranty_months(item.warranty)
    if warranty_months is None:
        flags.append("WARRANTY_FORMAT_REVIEW")
    elif warranty_months < _COMMERCIAL_WARRANTY_REVIEW_MONTHS:
        flags.append("WARRANTY_REVIEW")
    if not item.payment_terms.strip():
        flags.append("PAYMENT_TERMS_REVIEW")
    return flags


def build_commercial_risk_review(
    commercial_data: Sequence[CommercialValue],
) -> list[dict[str, object]]:
    """Normalize commercial fields and expose exception flags for review."""
    rows: list[dict[str, object]] = []
    for item in commercial_data:
        price = _normalise_commercial_price(item.price)
        lead_time_weeks = _normalise_commercial_lead_time(item.lead_time)
        warranty_months = _normalise_warranty_months(item.warranty)
        flags = _commercial_risk_flags(item)
        rows.append(
            {
                "vendor": item.vendor,
                "price": price,
                "currency": item.currency.strip().upper(),
                "lead_time_weeks": lead_time_weeks,
                "warranty_months": warranty_months,
                "payment_terms": " ".join(item.payment_terms.split()),
                "claim_status": item.claim_status,
                "evidence": item.evidence,
                "flags": flags,
                "review_required": bool(flags),
            }
        )
    return rows


def build_report(
    requirements: Sequence[Requirement] | None = None,
    vendor_data: Sequence[VendorValue] | None = None,
    commercial_data: Sequence[CommercialValue] | None = None,
) -> dict[str, object]:
    """Return a machine-readable RFQ review report."""

    reqs = _normalise_requirements(requirements)
    values = _normalise_vendor_data(vendor_data)
    commercial = tuple(commercial_data or ())
    matrix = build_matrix(reqs, values)
    evidence_register = build_evidence_register(reqs, values, commercial)
    review_claims = [row for row in evidence_register if row["review_required"] == "YES"]
    deviations = [row for row in matrix if row["status"] == "DEVIATION"]
    unverified = [row for row in matrix if row["status"] == "UNVERIFIED"]
    vendors = tuple(dict.fromkeys(item.vendor for item in values))

    return {
        "product": "industrial-rfq-intelligence",
        "workflow": "rfq-compliance-review",
        "evidence_policy": (
            "Only explicit supporting quotation evidence may be marked VERIFIED; "
            "missing or unsupported claims remain UNVERIFIED."
        ),
        "summary": {
            "requirements_checked": len(reqs),
            "vendors_checked": len(vendors),
            "matrix_rows": len(matrix),
            "deviations": len(deviations),
            "unverified_fields": len(unverified),
            "commercial_records": len(commercial),
            "evidence_records": len(evidence_register),
            "claims_requiring_review": len(review_claims),
        },
        "matrix": matrix,
        "commercial_comparison": [asdict(item) for item in commercial],
        "commercial_risk_review": build_commercial_risk_review(commercial),
        "evidence_register": evidence_register,
        "review_actions": [
            {
                "vendor": row["vendor"],
                "parameter": row["parameter"],
                "offered": row["offered"],
                "required": row["required"],
                "action": "Engineer review required",
                "evidence": row["evidence"],
            }
            for row in deviations
        ],
    }


def render_report(report: dict[str, object]) -> str:
    """Render a concise human-readable RFQ review."""

    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "Industrial RFQ Intelligence — RFQ compliance review",
        "=" * 62,
        "Workflow: RFQ → requirement extraction → compliance review",
        "",
    ]
    matrix = report["matrix"]
    assert isinstance(matrix, list)
    for row in matrix:
        lines.append(
            f"{row['requirement']} | {row['vendor']:8} | "
            f"{row['parameter']:18} | required={row['required']:5} | "
            f"offered={row['offered']:7} | {row['status']:10} | "
            f"{row['evidence']}"
        )
    lines.extend(
        [
            "",
            f"Requirements checked: {summary['requirements_checked']}",
            f"Vendors checked: {summary['vendors_checked']}",
            f"Deviations requiring engineer review: {summary['deviations']}",
            f"Unverified fields: {summary['unverified_fields']}",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, object], output: str | Path) -> None:
    """Write a JSON report to disk, creating the parent directory if needed."""

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "RFQ_SCHEMA_VERSION",
    "SUPPORTED_RFQ_SCHEMA_VERSIONS",
    "EvidenceProvenance",
    "ClaimStatus",
    "DEFAULT_REQUIREMENTS",
    "DEFAULT_VENDOR_DATA",
    "Requirement",
    "VendorValue",
    "CommercialValue",
    "DocumentPage",
    "extract_document_pages",
    "extract_document_pages_with_ocr",
    "document_text",
    "build_matrix",
    "build_evidence_register",
    "build_commercial_risk_review",
    "build_report",
    "load_rfq_input",
    "extract_rfq_with_llm",
    "extract_rfq_documents_with_llm",
    "render_report",
    "write_report",
]


def extract_rfq_documents_with_llm(
    pool: object,
    rfq_document: str | Path,
    quotation_documents: Sequence[dict[str, str | Path]],
    *,
    use_markdown: bool = True,
    use_ocr: bool = False,
    ocr_language: str = "eng",
) -> tuple[list[Requirement], list[VendorValue], list[CommercialValue]]:
    """Extract RFQ/quotations through the canonical document normalization layer.

    MarkItDown is the default parser. The legacy page extractor remains available
    as an explicit fallback, while the existing OCR path is retained for cases
    where a local Tesseract workflow is preferred.
    """
    if use_markdown and use_ocr:
        raise ValueError("use_markdown and use_ocr cannot be enabled together")

    if use_markdown:
        from .document_normalizer import normalize_document

        rfq_normalized = normalize_document(rfq_document)
        rfq_text = (
            f"[SOURCE: {rfq_normalized.source}]\n"
            f"{rfq_normalized.markdown}"
        )
        quotations: list[dict[str, str]] = []
        for index, item in enumerate(quotation_documents):
            vendor = str(item.get("vendor", "")).strip()
            path = item.get("path")
            if not vendor or path is None:
                raise ValueError(f"quotation_documents[{index}] requires vendor and path")
            normalized = normalize_document(path)
            text = normalized.markdown.strip()
            if not text:
                raise ValueError(f"quotation document is empty: {path}")
            quotations.append({
                "vendor": vendor,
                "text": f"[SOURCE: {normalized.source}]\n{text}",
                "evidence_prefix": f"{Path(path).name}",
            })
        return extract_rfq_with_llm(pool, rfq_text, quotations)

    page_extractor = extract_document_pages_with_ocr if use_ocr else extract_document_pages
    rfq_pages = (
        page_extractor(rfq_document, language=ocr_language)
        if use_ocr
        else page_extractor(rfq_document)
    )
    rfq_text = document_text(rfq_pages)
    quotations = []
    for index, item in enumerate(quotation_documents):
        vendor = str(item.get("vendor", "")).strip()
        path = item.get("path")
        if not vendor or path is None:
            raise ValueError(f"quotation_documents[{index}] requires vendor and path")
        pages = (
            page_extractor(path, language=ocr_language)
            if use_ocr
            else page_extractor(path)
        )
        text = document_text(pages)
        if not text.strip():
            raise ValueError(f"quotation document is empty: {path}")
        quotations.append({
            "vendor": vendor,
            "text": text,
            "evidence_prefix": f"{Path(path).name}",
        })
    return extract_rfq_with_llm(pool, rfq_text, quotations)

def extract_rfq_with_llm(pool: object, rfq_text: str, quotations: Sequence[dict[str, str]]) -> tuple[list[Requirement], list[VendorValue], list[CommercialValue]]:
    """Extract structured RFQ data with the gateway, then validate it locally.

    The model is an extractor only. Compliance status is calculated later by
    build_matrix from the extracted values and their evidence.
    """
    if not rfq_text.strip():
        raise ValueError("RFQ text must not be empty")
    if not quotations:
        raise ValueError("at least one quotation is required")

    quote_payload = []
    for index, quote in enumerate(quotations):
        vendor = str(quote.get("vendor", "")).strip()
        text = str(quote.get("text", "")).strip()
        evidence_prefix = str(quote.get("evidence_prefix", f"{vendor} quotation")).strip()
        if not vendor or not text:
            raise ValueError(f"quotations[{index}] requires vendor and text")
        quote_payload.append({"vendor": vendor, "text": text, "evidence_prefix": evidence_prefix})

    schema = {
        "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
        "vendor_data": [{"vendor": "Vendor A", "parameter": "Rated voltage",
                         "value": "415 V", "evidence": "Vendor A quotation, section 2",
                         "claim_status": "VERIFIED", "provenance": {"source": "Vendor A quotation", "page": 2, "section": "Technical data", "table": None, "cell": None}}],
        "commercial_data": [{"vendor": "Vendor A", "price": "10000", "currency": "USD", "lead_time": "8 weeks", "warranty": "12 months", "payment_terms": "30% advance", "evidence": "Vendor A quotation, commercial section", "claim_status": "VERIFIED", "provenance": {"source": "Vendor A quotation", "page": None, "section": "Commercial", "table": None, "cell": None}}],
    }
    system = (
        "You are an engineering document extraction component. Extract only facts explicitly stated "
        "in the supplied RFQ and quotations. Never infer missing values. Every vendor value must include "
        "a concise source/evidence reference. Return exactly one JSON object matching this schema: "
        + json.dumps(schema, ensure_ascii=False)
        + ". Use claim_status VERIFIED only when the supplied quotation explicitly supports the value; "
        "otherwise use UNVERIFIED. Do not calculate compliance."
    )
    prompt = system + "\\n\\nRFQ:\\n" + rfq_text + "\\n\\nQUOTATIONS:\\n" + json.dumps(quote_payload, ensure_ascii=False)
    ask = getattr(pool, "ask", None)
    if not callable(ask):
        raise TypeError("pool must provide an ask() method")
    reply = ask(prompt)
    raw = getattr(reply, "text", reply)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("LLM extraction returned an empty response")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM extraction returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM extraction must return a JSON object")
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        temporary_path = Path(handle.name)
    try:
        return load_rfq_input(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)