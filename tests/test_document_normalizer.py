from __future__ import annotations

from pathlib import Path

from freellmpool.document_normalizer import NormalizedDocument, normalize_document


def test_markitdown_normalizes_markdown_input(tmp_path: Path) -> None:
    source = tmp_path / "quote.md"
    source.write_text("# Motor\n\nRated voltage: 415 V\n", encoding="utf-8")

    result = normalize_document(source)

    assert isinstance(result, NormalizedDocument)
    assert result.source == str(source)
    assert result.page_count == 1
    assert "# Motor" in result.markdown
    assert "Rated voltage: 415 V" in result.markdown


def test_markitdown_normalizes_pdf_with_page_provenance(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    source = tmp_path / "quote.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as handle:
        writer.write(handle)

    result = normalize_document(source)

    assert result.page_count == 2
    assert result.source == str(source)
    assert result.markdown == ""


def test_markitdown_supports_image_inputs_without_changing_provenance(tmp_path: Path) -> None:
    from PIL import Image

    source = tmp_path / "plate.png"
    Image.new("RGB", (20, 20), "white").save(source)

    result = normalize_document(source)

    assert result.source == str(source)
    assert result.page_count == 1
