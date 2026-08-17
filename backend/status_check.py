#!/usr/bin/env python3
"""
Detailed infrastructure status check for Redis RQ, Worker, and MongoDB Atlas
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

# Load environment variables
dotenv_path = Path(__file__).resolve().parent / "backend" / ".env"
load_dotenv(dotenv_path)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

print("=" * 80)
print("INFRASTRUCTURE STATUS CHECK")
print("=" * 80)

# Import backend modules
import sys
sys.path.insert(0, '/app')
from database import get_database

db = get_database()

print("\n[1] DOCUMENTS STATUS")
print("-" * 80)
docs = list(db.documents.find({}, {'id': 1, 'filename': 1, 'category': 1, 'status': 1, 'chunks': 1}))
for doc in docs:
    doc_id = doc.get("id", "?")
    filename = doc.get("filename", "unknown")[:40]
    category = doc.get("category", "[None]")
    status = doc.get("status", "?")
    chunks = doc.get("chunks", 0)
    print(f"  ID {doc_id}: {filename:40s} | Category: {category:20s} | Status: {status:10s} | Chunks: {chunks}")

print("\n[2] VECTOR DISTRIBUTION BY CATEGORY")
print("-" * 80)
pipeline = [
    {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
categories = list(db.document_vectors.aggregate(pipeline))
total = sum(c['count'] for c in categories)
for cat in categories:
    name = cat['_id'] or '[None]'
    cnt = cat['count']
    pct = 100 * cnt / total if total > 0 else 0
    print(f"  {name:25s}: {cnt:4d} vectors ({pct:.1f}%)")

print("\n[3] INDEXING JOBS STATUS")
print("-" * 80)
processing = db.documents.count_documents({'status': 'processing'})
indexed = db.documents.count_documents({'status': 'indexed'})
failed = db.documents.count_documents({'status': 'failed'})
print(f"  Processing: {processing}")
print(f"  Indexed:    {indexed}")
print(f"  Failed:     {failed}")

print("\n[4] REDIS QUEUE STATUS")
print("-" * 80)
try:
    from redis import Redis
    from rq import Queue
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("rag-indexing", connection=redis_conn)
    print(f"  Pending jobs in rag-indexing queue: {len(queue)}")
    print(f"  Redis connection: OK")
except Exception as e:
    print(f"  Redis connection: ERROR - {e}")

print("\n[5] MONGODB COLLECTIONS")
print("-" * 80)
collections = db.list_collection_names()
print(f"  Total collections: {len(collections)}")
for col in sorted(collections):
    count = db[col].count_documents({})
    print(f"    {col:25s}: {count:6d} documents")

print("\n" + "=" * 80)
print("STATUS CHECK COMPLETE")
print("=" * 80)
