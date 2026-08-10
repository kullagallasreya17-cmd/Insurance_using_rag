import re
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from pypdf import PdfReader

from rag.ocr_loader import load_image_document
from rag.text_splitter import split_documents
from rag.vectorstore import get_mongo_vector_store


def _load_supported_file(file_path: Path, content_type: str):
    if content_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        return PyPDFLoader(str(file_path)).load()

    if content_type.startswith("image/") or file_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return load_image_document(file_path)

    raise RuntimeError("Unsupported file type. Upload PDF, PNG, JPG, or JPEG files.")


def extract_document_preview(file_path: Path, content_type: str):
    if content_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(str(file_path))
            pages = []
            for page in reader.pages[:2]:
                text = page.extract_text() or ""
                pages.append(text.strip())
            return "\n\n".join(page for page in pages if page)[:2000]
        except Exception:
            return ""

    return ""


def _count_words_in_pages(pages):
    total_words = 0
    for page in pages:
        text = (getattr(page, "page_content", "") or "").strip()
        if not text:
            continue
        total_words += len(re.findall(r"\b\w+\b", text))
    return total_words


def index_document(file_path: Path, document_type: str, category: str, content_type: str):
    started_at = __import__("time").perf_counter()
    pages = _load_supported_file(file_path, content_type)

    if not pages:
        raise ValueError(
            "No readable text found in the uploaded PDF. Please upload a text-based PDF or a PDF with extractable content."
        )

    valid_pages = []
    for page in pages:
        content = (page.page_content or "").strip()
        if not content:
            continue

        page.metadata["document_type"] = document_type
        page.metadata["category"] = category
        page.metadata["source"] = str(file_path)
        valid_pages.append(page)

    if not valid_pages:
        raise ValueError(
            "No readable text found in the uploaded PDF. Please upload a text-based PDF or a PDF with extractable content."
        )

    chunks = split_documents(valid_pages)
    if not chunks:
        raise ValueError(
            "No readable text found in the uploaded PDF. Please upload a text-based PDF or a PDF with extractable content."
        )

    vector_store = get_mongo_vector_store()
    texts = [chunk.page_content for chunk in chunks]
    metadatas = [chunk.metadata for chunk in chunks]
    vector_store.add_texts(texts=texts, metadatas=metadatas)

    word_count = _count_words_in_pages(valid_pages)

    return {
        "pages": len(valid_pages),
        "chunks": len(chunks),
        "word_count": word_count,
        "processing_time_seconds": round(__import__("time").perf_counter() - started_at, 2),
    }
