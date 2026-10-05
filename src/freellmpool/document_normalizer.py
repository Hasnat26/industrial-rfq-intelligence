"""Universal document normalization through Microsoft's MarkItDown.

The adapter keeps the product's evidence-first model while delegating file
format parsing and Markdown rendering to the maintained MarkItDown package.
PDF pages are converted independently so page provenance remains explicit.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader, PdfWriter


@dataclass(frozen=True)
class NormalizedDocument:
    """Markdown representation with source/page provenance."""

    source: str
    markdown: str
    page_count: int


def _markitdown() -> object:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise ValueError(
            "document normalization requires MarkItDown; install with: "
            "pip install 'industrial-rfq-intelligence[documents]'"
        ) from exc
    return MarkItDown()


def _convert_bytes(converter: object, data: bytes, filename: str) -> str:
    try:
        from markitdown import StreamInfo

        result = converter.convert_stream(
            io.BytesIO(data),
            stream_info=StreamInfo(
                extension=Path(filename).suffix,
                filename=Path(filename).name,
            ),
        )
    except Exception as exc:
        raise ValueError(f"MarkItDown conversion failed for '{filename}': {exc}") from exc
    markdown = getattr(result, "markdown", None)
    if not isinstance(markdown, str):
        markdown = getattr(result, "text_content", None)
    if not isinstance(markdown, str):
        raise ValueError(f"MarkItDown returned no Markdown content for '{filename}'")
    return markdown.strip()


def normalize_document(path: str | Path) -> NormalizedDocument:
    """Convert a supported local document into clean Markdown.

    PDFs are converted page-by-page to retain deterministic page provenance.
    Other MarkItDown-supported formats are converted as one logical page.
    """
    document = Path(path)
    if not document.is_file():
        raise ValueError(f"document not found: {document}")

    converter = _markitdown()
    suffix = document.suffix.casefold()

    if suffix != ".pdf":
        markdown = converter.convert(str(document)).markdown  # type: ignore[attr-defined]
        if not isinstance(markdown, str):
            raise ValueError(f"MarkItDown returned no Markdown content for '{document}'")
        return NormalizedDocument(str(document), markdown.strip(), 1)

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
            markdown = converter.convert(str(page_path)).markdown  # type: ignore[attr-defined]
            if not isinstance(markdown, str):
                raise ValueError(f"MarkItDown returned no Markdown for PDF page {number}")
            content = markdown.strip()
            if content:
                page_parts.append(f"## Page {number}\n\n{content}")

    return NormalizedDocument(
        source=str(document),
        markdown="\n\n".join(page_parts).strip(),
        page_count=len(reader.pages),
    )


__all__ = ["NormalizedDocument", "normalize_document"]
