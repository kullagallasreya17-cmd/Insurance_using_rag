#!/usr/bin/env python3
"""
Vector Database Query Tool for Insurance RAG
Access MongoDB Atlas vector search for stored embeddings and documents.

Usage:
    python query_vectordb.py
    python query_vectordb.py --query "vehicle insurance"
    python query_vectordb.py --delete-all
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from rag.vectorstore import get_mongo_collection, get_mongo_vector_store


def list_all_documents():
    """List current documents stored in MongoDB Atlas."""
    collection = get_mongo_collection()
    total_docs = collection.count_documents({})
    print(f"📦 MongoDB Atlas Collection: {collection.name}")
    print(f"📊 Total documents: {total_docs}")


def query_vectordb(question: str):
    """Query the MongoDB Atlas vector store for similar documents."""
    print(f"🔍 Searching for: '{question}'\n")

    try:
        db = get_mongo_vector_store()
        docs = db.similarity_search(question, k=5)

        if not docs:
            print("❌ No documents found")
            return

        print(f"✓ Found {len(docs)} matching documents:\n")
        for i, doc in enumerate(docs, 1):
            print(f"Result {i}:")
            print(f"  Content: {doc.page_content[:200]}...")
            print(f"  Metadata: {doc.metadata}\n")
    except Exception as e:
        print(f"❌ Error querying vector database: {str(e)}")


def delete_all_documents():
    """Delete all documents from the MongoDB Atlas collection."""
    collection = get_mongo_collection()
    result = collection.delete_many({})
    print(f"✓ Deleted {result.deleted_count} document(s)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--query" and len(sys.argv) > 2:
            query_vectordb(" ".join(sys.argv[2:]))
        elif sys.argv[1] == "--delete-all":
            delete_all_documents()
        else:
            print("Unknown command")
    else:
        list_all_documents()
