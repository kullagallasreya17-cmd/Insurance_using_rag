from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from rag.indexer import _count_words_in_pages, index_document


def test_blank_pdf_is_rejected_with_clear_error(tmp_path):
    file = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(file, "wb") as fh:
        writer.write(fh)

    with pytest.raises(ValueError, match="No readable text found in the uploaded PDF"):
        index_document(file, "policy", "vehicle_policy", "application/pdf")


def test_count_words_in_pages_counts_text_content():
    pages = [
        SimpleNamespace(page_content="Hello world from PDF page 1", metadata={}),
        SimpleNamespace(page_content="Second page has more words here", metadata={}),
        SimpleNamespace(page_content="", metadata={}),
    ]

    assert _count_words_in_pages(pages) == 12
