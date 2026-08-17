import re
import hashlib
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from pypdf import PdfReader

from rag.ocr_loader import load_image_document
from rag.text_splitter import split_documents
from rag.vectorstore import (
    get_mongo_vector_store,
    get_mongo_collection,
    MONGO_TEXT_KEY,
)


def _load_supported_file(file_path: Path, content_type: str):
    if content_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        return PyPDFLoader(str(file_path)).load()

    if content_type.startswith("image/") or file_path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
    }:
        return load_image_document(file_path)

    raise RuntimeError(
        "Unsupported file type. Upload PDF, PNG, JPG, or JPEG files."
    )


def extract_document_preview(file_path: Path, content_type: str):
    if content_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        try:
            reader = PdfReader(str(file_path))
            pages = []

            for page in reader.pages[:2]:
                text = page.extract_text() or ""
                pages.append(text.strip())

            return "\n\n".join(
                page for page in pages if page
            )[:2000]

        except Exception:
            return ""

    return ""


def _count_words_in_pages(pages):
    total_words = 0

    for page in pages:
        text = (
            getattr(page, "page_content", "") or ""
        ).strip()

        if not text:
            continue

        total_words += len(
            re.findall(r"\b\w+\b", text)
        )

    return total_words


def index_document(
    file_path: Path,
    document_type: str,
    category: str,
    content_type: str,
    document_id: int | None = None,
    filename: str | None = None,
):
    started_at = __import__("time").perf_counter()

    # ---------------------------------------------------------
    # 1. Load document
    # ---------------------------------------------------------
    pages = _load_supported_file(
        file_path,
        content_type,
    )

    if not pages:
        raise ValueError(
            "No readable text found in the uploaded PDF. "
            "Please upload a text-based PDF or a PDF with "
            "extractable content."
        )

    # ---------------------------------------------------------
    # 2. Validate pages and attach metadata
    # ---------------------------------------------------------
    valid_pages = []

    for page in pages:
        content = (
            page.page_content or ""
        ).strip()

        if not content:
            continue

        original_filename = filename or file_path.name
        page.metadata["document_type"] = document_type
        page.metadata["category"] = category
        page.metadata["source"] = str(file_path)
        page.metadata["filename"] = original_filename
        page.metadata["document_name"] = Path(original_filename).stem
        if document_id is not None:
            page.metadata["document_id"] = document_id

        valid_pages.append(page)

    if not valid_pages:
        raise ValueError(
            "No readable text found in the uploaded PDF. "
            "Please upload a text-based PDF or a PDF with "
            "extractable content."
        )

    # ---------------------------------------------------------
    # 3. Split document into chunks
    # ---------------------------------------------------------
    chunks = split_documents(valid_pages)

    if not chunks:
        raise ValueError(
            "No readable text found in the uploaded PDF. "
            "Please upload a text-based PDF or a PDF with "
            "extractable content."
        )

    print(f"{len(chunks)} chunks created.")

    # ---------------------------------------------------------
    # 4. Get MongoDB collection
    # ---------------------------------------------------------
    collection = get_mongo_collection()

    unique_texts = []
    unique_metadatas = []

    # ---------------------------------------------------------
    # 5. Calculate SHA256 fingerprint of the uploaded file
    # ---------------------------------------------------------
    sha256_digest = None

    try:
        hasher = hashlib.sha256()

        with open(file_path, "rb") as fh:
            for chunk_bytes in iter(
                lambda: fh.read(1024 * 1024),
                b"",
            ):
                hasher.update(chunk_bytes)

        sha256_digest = hasher.hexdigest()

    except Exception:
        sha256_digest = None

    # ---------------------------------------------------------
    # 6. Check whether the exact file was already indexed
    # ---------------------------------------------------------
    if sha256_digest:
        try:
            existing_file = collection.find_one(
                {"sha256": sha256_digest}
            )

            if existing_file:
                word_count = _count_words_in_pages(
                    valid_pages
                )

                print(
                    "Document already indexed "
                    "(SHA256 match). Skipping duplicate indexing."
                )

                return {
                    "pages": len(valid_pages),
                    "chunks": len(chunks),
                    "word_count": word_count,
                    "chunks_indexed": 0,
                    "status": "skipped",
                    "message": (
                        "This document has already been "
                        "indexed. Skipping duplicate indexing."
                    ),
                    "processing_time_seconds": round(
                        __import__("time").perf_counter()
                        - started_at,
                        2,
                    ),
                }

        except Exception as exc:
            # If the SHA256 database check fails,
            # continue with chunk-level duplicate checking.
            print(
                f"SHA256 duplicate check failed: {exc}. "
                "Continuing with chunk-level deduplication."
            )

    # ---------------------------------------------------------
    # 7. Check individual chunks for duplicates
    # ---------------------------------------------------------
    for chunk_index, chunk in enumerate(chunks, start=1):
        content = (
            chunk.page_content or ""
        ).strip()

        if not content:
            continue

        chunk.metadata["chunk_id"] = chunk_index
        chunk.metadata["chunk_count"] = len(chunks)

        # Attach file-level fingerprint to metadata
        if sha256_digest:
            try:
                chunk.metadata["sha256"] = sha256_digest
            except Exception:
                pass

        duplicate_query = {MONGO_TEXT_KEY: content}
        if sha256_digest:
            duplicate_query["sha256"] = sha256_digest
        elif document_id is not None:
            duplicate_query["document_id"] = document_id
        else:
            duplicate_query["source"] = str(file_path)

        # Check whether this exact chunk already exists for this document.
        # A global text-only check can skip valid chunks from another upload
        # and preserve stale category/source metadata.
        try:
            exists = collection.find_one(
                duplicate_query
            )

        except Exception as exc:
            print(
                f"Chunk duplicate check failed: {exc}. "
                "Treating chunk as new."
            )
            exists = None

        if exists:
            continue

        unique_texts.append(content)
        unique_metadatas.append(chunk.metadata)

    # ---------------------------------------------------------
    # 8. If every chunk already exists, skip cleanly
    # ---------------------------------------------------------
    if not unique_texts:
        word_count = _count_words_in_pages(
            valid_pages
        )

        print(
            "All document chunks are already indexed. "
            "Skipping duplicate indexing."
        )

        return {
            "pages": len(valid_pages),
            "chunks": len(chunks),
            "word_count": word_count,
            "chunks_indexed": 0,
            "status": "skipped",
            "message": (
                "All document chunks are already indexed. "
                "Skipping duplicate indexing."
            ),
            "processing_time_seconds": round(
                __import__("time").perf_counter()
                - started_at,
                2,
            ),
        }

    # ---------------------------------------------------------
    # 9. Index only new chunks into MongoDB
    # ---------------------------------------------------------
    vector_store = get_mongo_vector_store()

    vector_store.add_texts(
        texts=unique_texts,
        metadatas=unique_metadatas,
    )

    # ---------------------------------------------------------
    # 10. Calculate word count
    # ---------------------------------------------------------
    word_count = _count_words_in_pages(
        valid_pages
    )

    # ---------------------------------------------------------
    # 11. Return indexing result
    # ---------------------------------------------------------
    return {
        "pages": len(valid_pages),
        "chunks": len(chunks),
        "chunks_indexed": len(unique_texts),
        "word_count": word_count,
        "status": "indexed",
        "message": (
            f"Successfully indexed {len(unique_texts)} "
            f"new chunks."
        ),
        "processing_time_seconds": round(
            __import__("time").perf_counter()
            - started_at,
            2,
        ),
    }
