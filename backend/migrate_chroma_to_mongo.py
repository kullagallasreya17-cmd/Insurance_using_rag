#!/usr/bin/env python3
"""
Legacy migration script:
  1) Load all vectors + metadata from the local ChromaDB collection.
  2) Lookup the matching MongoDB document metadata row by document_id.
  3) Merge both sources into one MongoDB Atlas Vector Search document.
  4) Bulk-insert into MongoDB Atlas using pymongo.
  5) Log and skip any record that cannot merge or insert.
  6) Print a final summary: migrated / skipped / failed.

Example usage:
    python backend/migrate_chroma_to_mongo.py

Environment variables:
    MONGO_URI=mongodb+srv://trainerAdmin:<db_password>@cluster0.y4woi43.mongodb.net/?appName=Cluster0
    MONGO_DB=insurance
    MONGO_COLLECTION=document_vectors
    CHROMA_COLLECTION=documents
    CHROMA_PERSIST_DIR=backend/vector_db

Notes:
- This legacy migration tool is retained for one-time transfer from local ChromaDB to MongoDB Atlas Vector Search.
- It is not required by the current application runtime.
- This script expects the Chroma metadata to contain a `document_id` field, matching the MongoDB `documents.id` value.
- If the metadata does not include it, the document is skipped with a log entry.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import DocumentRecord

try:
    from chromadb import PersistentClient
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("chromadb is required for this migration script.") from exc


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mongo_migration")


MONGO_URI = os.getenv(
    "MONGO_URI",
    os.getenv("dbpassword") and f"mongodb+srv://trainerAdmin:{os.getenv('dbpassword')}@cluster0.y4woi43.mongodb.net/?appName=Cluster0" or "mongodb+srv://trainerAdmin:sw4ccCOaThn1cdZu@cluster0.y4woi43.mongodb.net/?appName=Cluster0",
)
MONGO_DB = os.getenv("MONGO_DB", "insurance")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "document_vectors")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(Path(__file__).resolve().parent / "vector_db"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))


def to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            return value
    return str(value)


def fetch_chroma_records(collection_name: str) -> list[dict[str, Any]]:
    """Return all vectors + metadata from the local persistent Chroma collection."""
    client = PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = client.get_collection(name=collection_name)
    results = collection.get(include=["ids", "documents", "metadatas", "embeddings"])

    items: list[dict[str, Any]] = []
    ids = results.get("ids") or []
    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    embeddings = results.get("embeddings") or []

    for idx, chroma_id in enumerate(ids):
        item = {
            "id": chroma_id,
            "document": documents[idx] if idx < len(documents) else "",
            "metadata": metadatas[idx] if idx < len(metadatas) else {},
            "embedding": embeddings[idx] if idx < len(embeddings) else None,
        }
        items.append(item)

    logger.info("Fetched %s records from Chroma collection '%s'", len(items), collection_name)
    return items


def fetch_mongo_document(mongo_db, document_id: int) -> DocumentRecord | None:
    """Fetch the matching MongoDB document metadata row by document_id."""
    record = mongo_db.documents.find_one({"id": document_id}, {"_id": 0})
    if not record:
        return None
    return DocumentRecord.from_mongo(record)


def build_mongo_document(chroma_item: dict[str, Any], file_record: DocumentRecord | None) -> dict[str, Any]:
    """Merge Chroma vector data and Mongo metadata into the vector-search schema."""
    meta = dict(chroma_item.get("metadata") or {})
    doc_id = meta.get("document_id") or meta.get("doc_id") or meta.get("source_id")

    if doc_id is None:
        raise ValueError("Missing document_id in Chroma metadata")

    try:
        document_id = int(doc_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid document_id value: {doc_id!r}") from exc

    if file_record is None:
        raise ValueError(f"No MongoDB document metadata found for document_id={document_id}")

    merged_meta = {**meta}
    merged_meta.setdefault("document_id", document_id)
    merged_meta.setdefault("filename", file_record.filename)
    merged_meta.setdefault("document_type", file_record.document_type)
    merged_meta.setdefault("category", file_record.category)
    merged_meta.setdefault("source", file_record.stored_path)
    merged_meta.setdefault("uploaded_by", file_record.uploaded_by)
    merged_meta.setdefault("status", file_record.status)
    merged_meta.setdefault("created_at", to_iso(file_record.created_at))

    mongo_doc = {
        "_id": f"{CHROMA_COLLECTION}:{chroma_item['id']}",
        "document_id": document_id,
        "chunk_id": chroma_item["id"],
        "collection_name": CHROMA_COLLECTION,
        "filename": file_record.filename,
        "stored_path": file_record.stored_path,
        "document_type": file_record.document_type,
        "category": file_record.category,
        "status": file_record.status,
        "pages": int(file_record.pages or 0),
        "chunks": int(file_record.chunks or 0),
        "word_count": int(file_record.word_count or 0),
        "processing_time_seconds": float(file_record.processing_time_seconds or 0.0),
        "version": int(file_record.version or 1),
        "uploaded_by": file_record.uploaded_by,
        "created_at": to_iso(file_record.created_at),
        "text": chroma_item.get("document") or "",
        "embedding": chroma_item.get("embedding"),
        "metadata": merged_meta,
    }

    return mongo_doc


def insert_batch(mongo_collection, batch: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert batch; if it fails, retry one-by-one and keep the per-record failures isolated."""
    if not batch:
        return 0, 0

    try:
        result = mongo_collection.insert_many(batch, ordered=False)
        return len(result.inserted_ids), 0
    except Exception as exc:  # fallback to record-level inserts
        logger.warning("Bulk insert failed; retrying record-by-record: %s", exc)
        inserted = 0
        failed = 0

        for doc in batch:
            try:
                mongo_collection.insert_one(doc)
                inserted += 1
            except Exception as inner_exc:
                failed += 1
                logger.exception(
                    "Insert failed for document_id=%s chunk_id=%s: %s",
                    doc.get("document_id"),
                    doc.get("chunk_id"),
                    inner_exc,
                )

        return inserted, failed


def migrate() -> dict[str, int]:
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client[MONGO_DB]
    mongo_collection = mongo_db[MONGO_COLLECTION]

    chroma_items = fetch_chroma_records(CHROMA_COLLECTION)

    migrated = 0
    skipped = 0
    failed = 0
    current_batch: list[dict[str, Any]] = []

    for chroma_item in chroma_items:
        try:
            document_id = (chroma_item.get("metadata") or {}).get("document_id") or (chroma_item.get("metadata") or {}).get("doc_id")
            if document_id is None:
                skipped += 1
                logger.warning("Skipping Chroma chunk %s: no document_id metadata", chroma_item.get("id"))
                continue

            file_record = fetch_mongo_document(mongo_db, int(document_id))
            mongo_doc = build_mongo_document(chroma_item, file_record)
            current_batch.append(mongo_doc)

            if len(current_batch) >= BATCH_SIZE:
                inserted, batch_failed = insert_batch(mongo_collection, current_batch)
                migrated += inserted
                failed += batch_failed
                current_batch = []

        except Exception as exc:
            failed += 1
            logger.exception(
                "Failed to merge or insert Chroma chunk id=%s with document_id=%s: %s",
                chroma_item.get("id"),
                (chroma_item.get("metadata") or {}).get("document_id"),
                exc,
            )
            continue

    if current_batch:
        inserted, batch_failed = insert_batch(mongo_collection, current_batch)
        migrated += inserted
        failed += batch_failed

    summary = {
        "migrated": migrated,
        "skipped": skipped,
        "failed": failed,
    }
    logger.info("Migration summary: %s", json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    try:
        summary = migrate()
        print("\nMigration complete")
        print(f"migrated={summary['migrated']}")
        print(f"skipped={summary['skipped']}")
        print(f"failed={summary['failed']}")
    except Exception as exc:
        logger.exception("Migration failed unexpectedly: %s", exc)
        print(f"MIGRATION FAILED: {exc}")
        sys.exit(1)
