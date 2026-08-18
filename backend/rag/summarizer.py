import logging
import os
import re
from datetime import datetime
from pathlib import Path

from langchain_core.documents import Document

from rag.generator import _build_llm, _invoke_with_retries
from rag.vectorstore import MONGO_TEXT_KEY, get_mongo_collection


POLICY_SUMMARY_MAX_CHARS = int(os.getenv("POLICY_SUMMARY_MAX_CHARS", "12000"))
POLICY_SUMMARY_MAX_CHUNKS = int(os.getenv("POLICY_SUMMARY_MAX_CHUNKS", "24"))
POLICY_SUMMARY_NOT_AVAILABLE = "Policy summary is not available yet."


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _metadata_sort_key(item: dict) -> tuple:
    page = item.get("page") or item.get("page_label") or 0
    chunk_id = item.get("chunk_id") or 0
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    try:
        chunk_id = int(chunk_id)
    except (TypeError, ValueError):
        chunk_id = 0
    return page, chunk_id


def _load_policy_chunks(document: dict) -> list[Document]:
    collection = get_mongo_collection()
    document_id = document.get("id")
    queries = []
    if document_id is not None:
        queries.append({"document_id": document_id})

    stored_path = document.get("stored_path")
    storage_key = document.get("storage_key")
    filename = document.get("filename")
    source_candidates = [value for value in (stored_path, storage_key, filename) if value]
    for value in source_candidates:
        queries.append({"source": str(value)})
        queries.append({"source": {"$regex": re.escape(Path(str(value)).name) + "$"}})

    seen = set()
    records = []
    for query in queries:
        try:
            for item in collection.find(query, {MONGO_TEXT_KEY: 1, "_id": 0, "page": 1, "page_label": 1, "chunk_id": 1, "source": 1, "filename": 1, "category": 1, "document_type": 1, "document_id": 1}):
                text = _normalize_whitespace(item.get(MONGO_TEXT_KEY, ""))
                if not text:
                    continue
                key = (item.get("document_id"), item.get("source"), item.get("page"), item.get("chunk_id"), text[:120])
                if key in seen:
                    continue
                seen.add(key)
                records.append({**item, MONGO_TEXT_KEY: text})
        except Exception:
            logging.exception("Unable to load policy chunks for summary query=%s document_id=%s", query, document_id)

        if records:
            break

    records = sorted(records, key=_metadata_sort_key)[:POLICY_SUMMARY_MAX_CHUNKS]
    return [
        Document(
            page_content=item.get(MONGO_TEXT_KEY, ""),
            metadata={key: value for key, value in item.items() if key != MONGO_TEXT_KEY},
        )
        for item in records
    ]


def _build_summary_context(chunks: list[Document]) -> str:
    context_parts = []
    total_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        text = _normalize_whitespace(chunk.page_content)
        if not text:
            continue
        page = chunk.metadata.get("page_label") or chunk.metadata.get("page") or "unknown"
        part = f"[Chunk {index} | page: {page}]\n{text}"
        if total_chars + len(part) > POLICY_SUMMARY_MAX_CHARS:
            remaining = POLICY_SUMMARY_MAX_CHARS - total_chars
            if remaining <= 200:
                break
            part = part[:remaining]
        context_parts.append(part)
        total_chars += len(part)
    return "\n\n".join(context_parts)


def _extractive_summary(filename: str, chunks: list[Document]) -> str:
    text = _normalize_whitespace(" ".join(chunk.page_content for chunk in chunks if chunk.page_content))
    if not text:
        return POLICY_SUMMARY_NOT_AVAILABLE

    sentences = re.split(r"(?<=[.!?])\s+", text)
    useful = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 40]
    selected = useful[:5] if useful else [text[:900]]
    summary = " ".join(selected)
    if len(summary) > 1200:
        summary = summary[:1197].rstrip() + "..."
    return f"{filename}: {summary}"


def generate_policy_summary(document: dict) -> dict:
    filename = document.get("filename") or "uploaded policy"
    if document.get("document_type") != "policy":
        return {
            "summary": "",
            "summary_status": "skipped",
            "summary_error": None,
            "summary_generated_at": None,
        }

    chunks = _load_policy_chunks(document)
    if not chunks:
        return {
            "summary": POLICY_SUMMARY_NOT_AVAILABLE,
            "summary_status": "missing_context",
            "summary_error": "No indexed chunks found for this policy.",
            "summary_generated_at": datetime.utcnow(),
        }

    if not os.getenv("GOOGLE_API_KEY"):
        return {
            "summary": _extractive_summary(filename, chunks),
            "summary_status": "generated_fallback",
            "summary_error": None,
            "summary_generated_at": datetime.utcnow(),
        }

    context = _build_summary_context(chunks)
    prompt = f"""
You are an insurance policy summarization assistant.

Use ONLY the uploaded policy context below.
Do not use general insurance knowledge.
Do not invent benefits, exclusions, premiums, waiting periods, or claim requirements.
If a detail is not present, omit it.

Write a concise policy summary with these sections:
- Policy overview
- Key coverage or benefits
- Exclusions or limits
- Claim process or required documents
- Important dates, premiums, or conditions if present

Policy filename: {filename}
Policy category: {document.get("category")}

Uploaded policy context:
{context}

Summary:
"""

    try:
        llm = _build_llm(temperature=0.1)
        summary = _normalize_whitespace(_invoke_with_retries(llm, prompt))
        return {
            "summary": summary or _extractive_summary(filename, chunks),
            "summary_status": "generated",
            "summary_error": None,
            "summary_generated_at": datetime.utcnow(),
        }
    except Exception as exc:
        logging.exception("Policy summary generation failed for document_id=%s", document.get("id"))
        return {
            "summary": _extractive_summary(filename, chunks),
            "summary_status": "generated_fallback",
            "summary_error": str(exc),
            "summary_generated_at": datetime.utcnow(),
        }
