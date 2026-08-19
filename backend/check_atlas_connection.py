"""Verify the Atlas connection and vector-search compatibility."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv(Path(__file__).resolve().parent / ".env")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "insurance")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "document_vectors")
MONGO_INDEX_NAME = os.getenv("MONGO_INDEX_NAME", "vectorSearchIndex")
MONGO_EMBEDDING_KEY = os.getenv("MONGO_EMBEDDING_KEY", "embedding")


def main() -> None:
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is missing from backend/.env")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    collection = client[MONGO_DB][MONGO_COLLECTION]

    sample = collection.find_one(
        {MONGO_EMBEDDING_KEY: {"$exists": True}},
        {"_id": 0, MONGO_EMBEDDING_KEY: 1},
    )
    vector = (sample or {}).get(MONGO_EMBEDDING_KEY) or []

    print("ATLAS_CONNECTION=OK")
    print(f"DATABASE={MONGO_DB}")
    print(f"COLLECTION={MONGO_COLLECTION}")
    print(f"VECTOR_FIELD={MONGO_EMBEDDING_KEY}")
    print(f"VECTOR_COUNT={collection.count_documents({})}")
    print(f"SAMPLE_VECTOR_DIMENSION={len(vector) if isinstance(vector, list) else 'INVALID'}")

    matching_indexes = [
        index
        for index in collection.list_search_indexes()
        if index.get("name") == MONGO_INDEX_NAME
    ]
    print(f"SEARCH_INDEX_FOUND={bool(matching_indexes)}")

    if matching_indexes:
        index = matching_indexes[0]
        definition = index.get("latestDefinition") or index.get("definition") or {}
        fields = definition.get("fields", [])
        print(f"SEARCH_INDEX_STATUS={index.get('status', 'unknown')}")
        print(f"SEARCH_INDEX_VECTOR_FIELD={next((field.get('path') for field in fields if field.get('type') == 'vector'), 'missing')}")
        print(f"SEARCH_INDEX_VECTOR_DIMENSION={next((field.get('numDimensions') for field in fields if field.get('type') == 'vector'), 'missing')}")
        filter_fields = sorted(
            field.get("path")
            for field in fields
            if field.get("type") == "filter" and field.get("path")
        )
        print(f"SEARCH_INDEX_FILTER_FIELDS={','.join(filter_fields)}")


if __name__ == "__main__":
    main()