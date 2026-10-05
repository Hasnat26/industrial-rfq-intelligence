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


def test_markitdown_is_canonical_for_local_rfq_llm_ingestion(tmp_path: Path) -> None:
    from freellmpool.industrial import extract_rfq_documents_with_llm

    rfq = tmp_path / "rfq.md"
    quote = tmp_path / "quote.md"
    rfq.write_text("# RFQ\n\nRated voltage: 415 V\n", encoding="utf-8")
    quote.write_text("# Technical Data\n\nRated voltage: 415 V\n", encoding="utf-8")

    class Reply:
        text = """{
          "requirements": [{"tag": "R-01", "parameter": "Rated voltage", "required": "415 V"}],
          "vendor_data": [{"vendor": "Vendor A", "parameter": "Rated voltage", "value": "415 V", "evidence": "quote.md", "claim_status": "VERIFIED", "provenance": {"source": "quote.md", "page": 1}}],
          "commercial_data": []
        }"""

    class Pool:
        def __init__(self) -> None:
            self.prompt = ""

        def ask(self, prompt: str) -> Reply:
            self.prompt = prompt
            return Reply()

    pool = Pool()
    requirements, vendor_data, commercial = extract_rfq_documents_with_llm(
        pool,
        rfq,
        [{"vendor": "Vendor A", "path": quote}],
    )

    assert requirements[0].required == "415 V"
    assert vendor_data[0].value == "415 V"
    assert commercial == []
    assert "[SOURCE:" in pool.prompt
    assert "Rated voltage: 415 V" in pool.prompt
