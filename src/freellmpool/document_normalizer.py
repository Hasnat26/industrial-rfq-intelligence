"""Universal document normalization through Microsoft's MarkItDown.

MarkItDown is the canonical format parser. A local Tesseract fallback is used
for sparse/scanned PDFs and standalone document images so image-only engineering
documents also enter the same Markdown normalization boundary.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from markitdown import MarkItDown
from pypdf import PdfReader, PdfWriter


@dataclass(frozen=True)
class NormalizedDocument:
    """Markdown representation with source/page provenance."""

    source: str
    markdown: str
    page_count: int


def _markitdown() -> MarkItDown:
    return MarkItDown()


def _ocr_image(image: Any, *, language: str) -> str:
    """OCR one PIL image with the local Tesseract runtime."""
    if shutil.which("tesseract") is None:
        raise ValueError(
            "OCR fallback requires the Tesseract executable; install Tesseract "
            "and the package's 'ocr' dependencies"
        )
    try:
        import pytesseract
    except ImportError as exc:
        raise ValueError(
            "OCR fallback requires the 'ocr' optional dependencies; install with: "
            "pip install 'industrial-rfq-intelligence[ocr]'"
        ) from exc
    try:
        return str(pytesseract.image_to_string(image, lang=language)).strip()
    except Exception as exc:
        raise ValueError(f"Tesseract OCR failed: {exc}") from exc


def _ocr_pdf_page(document: Path, page_number: int, *, language: str) -> str:
    """Render one PDF page and OCR it at a deterministic 2x scale."""
    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            "PDF OCR requires the 'ocr' optional dependencies; install with: "
            "pip install 'industrial-rfq-intelligence[ocr]'"
        ) from exc
    try:
        pdf = fitz.open(str(document))
    except Exception as exc:
        raise ValueError(f"cannot open PDF for OCR: {document}") from exc
    try:
        if page_number < 1 or page_number > len(pdf):
            raise ValueError(f"PDF page out of range: {page_number}")
        page = pdf[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        return _ocr_image(image, language=language)
    finally:
        pdf.close()


def normalize_document(
    path: str | Path,
    *,
    ocr_fallback: bool = True,
    ocr_language: str = "eng",
    ocr_min_text_chars: int = 20,
) -> NormalizedDocument:
    """Convert a supported local document into clean Markdown.

    PDFs are converted page-by-page to retain deterministic page provenance.
    Sparse PDF pages and standalone images fall back to local OCR when enabled.
    Other MarkItDown-supported formats are converted as one logical page.
    """
    document = Path(path)
    if not document.is_file():
        raise ValueError(f"document not found: {document}")
    if ocr_min_text_chars < 0:
        raise ValueError("ocr_min_text_chars must be non-negative")
    if not ocr_language.strip():
        raise ValueError("ocr_language must not be empty")

    converter = _markitdown()
    suffix = document.suffix.casefold()

    if suffix != ".pdf":
        image_suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
        try:
            markdown = converter.convert(str(document)).markdown
        except Exception as exc:
            if not (ocr_fallback and suffix in image_suffixes):
                raise ValueError(f"MarkItDown conversion failed for '{document}'") from exc
            markdown = ""
        if not isinstance(markdown, str):
            raise ValueError(f"MarkItDown returned no Markdown content for '{document}'")
        content = markdown.strip()
        if ocr_fallback and suffix in image_suffixes:
            try:
                from PIL import Image
            except ImportError as exc:
                raise ValueError(
                    "image OCR requires the 'ocr' optional dependencies; install with: "
                    "pip install 'industrial-rfq-intelligence[ocr]'"
                ) from exc
            with Image.open(document) as image:
                ocr_text = _ocr_image(image.convert("RGB"), language=ocr_language)
            if ocr_text:
                content = ocr_text
        return NormalizedDocument(str(document), content, 1)

    try:
        reader = PdfReader(str(document))
    except Exception as exc:
        raise ValueError(f"cannot read PDF: {document}") from exc
    if not reader.pages:
        raise ValueError(f"PDF contains no pages: {document}")

    page_parts: list[str] = []
    with TemporaryDirectory(prefix="industrial-rfq-markitdown-") as temp_dir:
        for number, page in enumerate(reader.pages, start=1):
            writer = PdfWriter()
            writer.add_page(page)
            page_path = Path(temp_dir) / f"page-{number}.pdf"
            with page_path.open("wb") as handle:
                writer.write(handle)
            markdown = converter.convert(str(page_path)).markdown
            if not isinstance(markdown, str):
                raise ValueError(f"MarkItDown returned no Markdown for PDF page {number}")
            content = markdown.strip()
            if ocr_fallback and len(content) < ocr_min_text_chars:
                ocr_text = _ocr_pdf_page(document, number, language=ocr_language)
                if ocr_text:
                    content = ocr_text
            if content:
                page_parts.append(f"## Page {number}\n\n{content}")

    return NormalizedDocument(
        source=str(document),
        markdown="\n\n".join(page_parts).strip(),
        page_count=len(reader.pages),
    )


__all__ = ["NormalizedDocument", "normalize_document"]
