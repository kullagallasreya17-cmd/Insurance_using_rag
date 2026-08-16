import re
import hashlib
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from pypdf import PdfReader

from rag.ocr_loader import load_image_document
from rag.text_splitter import split_documents
from rag.vectorstore import get_mongo_vector_store, get_mongo_collection, MONGO_TEXT_KEY


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

    # Deduplicate chunk texts against existing stored chunks to avoid duplicate indexing
    collection = get_mongo_collection()
    unique_texts = []
    unique_metadatas = []
    # Compute SHA256 fingerprint of the file to detect exact-file duplicates
    sha256_digest = None
    try:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk_bytes in iter(lambda: fh.read(1024 * 1024), b""):
                hasher.update(chunk_bytes)
        sha256_digest = hasher.hexdigest()
    except Exception:
        sha256_digest = None

    if sha256_digest:
        # If the collection already contains this file fingerprint, skip indexing.
        try:
            if collection.find_one({"sha256": sha256_digest}):
                raise ValueError("This document appears to have already been indexed (sha256 match).")
        except ValueError:
            raise
        except Exception:
            # If the DB check fails, continue with conservative per-chunk deduping below.
            pass
    for chunk in chunks:
        content = (chunk.page_content or "").strip()
        if not content:
            continue

        # Attach file-level fingerprint so retrieval and dedup can use it later
        if sha256_digest:
            try:
                chunk.metadata["sha256"] = sha256_digest
            except Exception:
                pass

        # Use exact match on the text key to detect duplicate chunks (conservative)
        try:
            exists = collection.find_one({MONGO_TEXT_KEY: content})
        except Exception:
            exists = None

        if exists:
            continue

        unique_texts.append(content)
        unique_metadatas.append(chunk.metadata)

    if not unique_texts:
        raise ValueError(
            "All document text chunks appear to be duplicates of existing indexed content. Skipping indexing."
        )

    vector_store = get_mongo_vector_store()
    vector_store.add_texts(texts=unique_texts, metadatas=unique_metadatas)

    word_count = _count_words_in_pages(valid_pages)

    return {
        "pages": len(valid_pages),
        "chunks": len(chunks),
        "word_count": word_count,
        "processing_time_seconds": round(__import__("time").perf_counter() - started_at, 2),
    }
