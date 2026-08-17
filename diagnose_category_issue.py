#!/usr/bin/env python3
"""
Comprehensive diagnostic script to trace category parameter through the entire pipeline.
Checks: documents collection, vector_store indexed docs, and verifies category preservation.
"""
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timedelta

# Load environment variables
dotenv_path = Path(__file__).resolve().parent / "backend" / ".env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "insurance")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

print("=" * 70)
print("CATEGORY PIPELINE DIAGNOSTIC REPORT")
print("=" * 70)

# 1. Check documents collection
print("\n[1] DOCUMENTS COLLECTION ANALYSIS")
print("-" * 70)
documents_col = db["documents"]
total_docs = documents_col.count_documents({})
print(f"Total documents in collection: {total_docs}")

# Group by category
from bson.son import SON
pipeline = [
    {"$group": {
        "_id": "$category",
        "count": {"$sum": 1},
        "sample_files": {"$push": "$filename"},
    }},
    {"$sort": {"count": -1}}
]
category_breakdown = list(documents_col.aggregate(pipeline))
print("\nDocuments by category:")
for entry in category_breakdown:
    category = entry["_id"] or "[None/Missing]"
    count = entry["count"]
    samples = entry["sample_files"][:2]  # First 2 samples
    print(f"  {category:25s}: {count:4d} documents (samples: {samples})")

# 2. Check document_vectors collection
print("\n[2] VECTOR COLLECTION ANALYSIS")
print("-" * 70)
vectors_col = db["document_vectors"]
total_vectors = vectors_col.count_documents({})
print(f"Total vectors in collection: {total_vectors}")

# Group by category
pipeline = [
    {"$group": {
        "_id": "$category",
        "count": {"$sum": 1},
    }},
    {"$sort": {"count": -1}}
]
vector_breakdown = list(vectors_col.aggregate(pipeline))
print("\nVectors by category:")
for entry in vector_breakdown:
    category = entry["_id"] or "[None/Missing]"
    count = entry["count"]
    percent = f"{100 * count / total_vectors:.1f}%"
    print(f"  {category:25s}: {count:4d} vectors ({percent})")

# 3. Check for mismatches between documents and vectors
print("\n[3] DOCUMENT-VECTOR CORRESPONDENCE CHECK")
print("-" * 70)
mismatches = []
for doc in documents_col.find().limit(20):  # Sample first 20 documents
    doc_id = doc["id"]
    doc_category = doc.get("category", "[None]")
    doc_filename = doc.get("filename")
    doc_status = doc.get("status")
    
    # Find vectors for this document
    vectors_for_doc = vectors_col.count_documents(
        {"source": {"$regex": str(doc_id)}}
    )
    
    if vectors_for_doc == 0:
        # Check if document is not yet indexed
        if doc_status not in ["indexed", "processing"]:
            continue
        mismatches.append({
            "document_id": doc_id,
            "filename": doc_filename,
            "category": doc_category,
            "status": doc_status,
            "vectors_found": 0,
            "issue": "Document marked as indexed but no vectors found"
        })

print(f"\nSampling 20 documents for correspondence...")
print(f"Found {len(mismatches)} potential issues:")
for mismatch in mismatches:
    print(f"  [{mismatch['issue']}]")
    print(f"    Document: {mismatch['filename']} (id={mismatch['document_id']})")
    print(f"    Category: {mismatch['category']}, Status: {mismatch['status']}")
    print(f"    Vectors indexed: {mismatch['vectors_found']}")

# 4. Sample recent vectors
print("\n[4] SAMPLE VECTORS - RECENT 5")
print("-" * 70)
recent_vectors = list(vectors_col.find()
    .sort("_id", -1)
    .limit(5))

for i, vector in enumerate(recent_vectors, 1):
    print(f"\nVector {i}:")
    print(f"  Category: {vector.get('category', '[None]')}")
    print(f"  Document Type: {vector.get('document_type', '[None]')}")
    print(f"  Source: {vector.get('source', '[Unknown]')[:60]}")
    text_preview = (vector.get('textContent', '')[:80]).replace('\n', ' ')
    print(f"  Text preview: {text_preview}...")

# 5. Check for MongoDB field existence
print("\n[5] FIELD COMPLETENESS CHECK")
print("-" * 70)
sample_vector = vectors_col.find_one({})
if sample_vector:
    print("Fields present in typical vector document:")
    for field in sorted(sample_vector.keys()):
        if field != "vectorContent":  # Don't print embeddings
            value = sample_vector[field]
            if isinstance(value, (list, dict)):
                print(f"  {field}: <{type(value).__name__} object>")
            else:
                print(f"  {field}: {value}")
else:
    print("No vectors found in collection!")

# 6. Test retrieval by category
print("\n[6] RETRIEVAL TEST BY CATEGORY")
print("-" * 70)
categories_to_test = ["vehicle_policy", "health_policy", "other"]
for category in categories_to_test:
    count = vectors_col.count_documents({"category": category})
    if count > 0:
        sample = vectors_col.find_one({"category": category})
        print(f"\n{category}: {count} vectors")
        print(f"  Sample text: {sample.get('textContent', '')[:100]}...")
    else:
        print(f"\n{category}: NO VECTORS FOUND")

# 7. Check for "other" documents
print("\n[7] INVESTIGATION: 'OTHER' CATEGORY")
print("-" * 70)
other_count = vectors_col.count_documents({"category": "other"})
if other_count > 0:
    print(f"\nFound {other_count} vectors in 'other' category")
    print("Sampling 3 documents from 'other':")
    for i, doc in enumerate(vectors_col.find({"category": "other"}).limit(3), 1):
        print(f"\n  Sample {i}:")
        print(f"    Document Type: {doc.get('document_type')}")
        print(f"    Source: {doc.get('source', '')[:60]}")
        print(f"    Text: {doc.get('textContent', '')[:80]}...")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
