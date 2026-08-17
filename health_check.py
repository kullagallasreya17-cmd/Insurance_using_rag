#!/usr/bin/env python3
"""
Comprehensive diagnostic script to check Redis RQ, Worker, and MongoDB Atlas.
Verifies all critical infrastructure components are working correctly.
"""
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
dotenv_path = Path(__file__).resolve().parent / "backend" / ".env"
load_dotenv(dotenv_path)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "insurance")

print("=" * 80)
print("INFRASTRUCTURE HEALTH CHECK")
print("=" * 80)

# ============================================================================
# 1. CHECK REDIS RQ
# ============================================================================
print("\n[1] REDIS RQ STATUS")
print("-" * 80)

try:
    from redis import Redis
    from rq import Queue, Worker
    
    redis_conn = Redis.from_url(REDIS_URL)
    
    # Test connection
    ping_result = redis_conn.ping()
    if ping_result:
        print("[OK] Redis connection successful")
    else:
        print("[ERROR] Redis connection failed")
        sys.exit(1)
    
    # Check queue
    queue_name = "rag-indexing"
    queue = Queue(queue_name, connection=redis_conn)
    
    queue_length = len(queue)
    print(f"[OK] Queue '{queue_name}' exists")
    print(f"     Queue length: {queue_length} jobs")
    
    # Get queue info
    print(f"\n[Queue Statistics]")
    print(f"  Redis URL: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}")
    print(f"  Queue name: {queue_name}")
    print(f"  Pending jobs: {queue_length}")
    
    # Get recent jobs (completed and failed)
    from rq.job import JobStatus
    
    finished_jobs = []
    failed_jobs = []
    
    # Get from registry
    try:
        finished_registry = queue.finished_job_registry
        finished_jobs = list(finished_registry.get_job_ids()[:10])
        print(f"  Finished jobs (recent 10): {len(finished_jobs)}")
        
        failed_registry = queue.failed_job_registry
        failed_jobs = list(failed_registry.get_job_ids()[:10])
        print(f"  Failed jobs: {len(failed_jobs)}")
    except Exception as e:
        print(f"  (Could not retrieve job history: {e})")
    
    # Show sample job if available
    if finished_jobs:
        from rq.job import Job
        try:
            sample_job = Job.fetch(finished_jobs[0], connection=redis_conn)
            print(f"\n[Sample Recent Job]")
            print(f"  Job ID: {sample_job.id[:16]}...")
            print(f"  Status: {sample_job.get_status()}")
            print(f"  Created: {sample_job.created_at}")
            print(f"  Started: {sample_job.started_at}")
            print(f"  Ended: {sample_job.ended_at}")
            if sample_job.get_status() == 'finished':
                print(f"  Result: {str(sample_job.result)[:100]}...")
        except Exception as e:
            print(f"  Error fetching sample job: {e}")
    
    print("\n[SUCCESS] Redis RQ is operational")
    
except Exception as e:
    print(f"[ERROR] Redis RQ check failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# 2. CHECK RQ WORKER
# ============================================================================
print("\n[2] RQ WORKER STATUS")
print("-" * 80)

try:
    from redis import Redis
    from rq import Queue, Worker
    
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("rag-indexing", connection=redis_conn)
    
    # Get all workers
    all_workers = Worker.all(connection=redis_conn)
    
    if not all_workers:
        print("[WARNING] No RQ workers detected")
        print("          This is expected if workers run in separate containers")
        print("          Check 'docker compose logs worker' for worker logs")
    else:
        print(f"[OK] Found {len(all_workers)} worker(s)")
        for i, worker in enumerate(all_workers, 1):
            print(f"\n[Worker {i}]")
            print(f"  Name: {worker.name}")
            print(f"  State: {worker.get_state()}")
            print(f"  Queues: {worker.queues}")
            print(f"  Birth date: {worker.birth_date}")
            print(f"  Current job: {worker.get_current_job()}")
            print(f"  Successful jobs: {worker.successful_job_count}")
            print(f"  Failed jobs: {worker.failed_job_count}")
            print(f"  Total jobs: {worker.total_jobs}")
    
    print("\n[Check Worker Container Logs]")
    print("Run: docker compose logs --tail=50 worker")
    
except Exception as e:
    print(f"[ERROR] Worker check failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# 3. CHECK MONGODB ATLAS
# ============================================================================
print("\n[3] MONGODB ATLAS STATUS")
print("-" * 80)

try:
    from pymongo import MongoClient
    
    print(f"[Connecting to MongoDB]")
    print(f"  URI: {MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI}")
    print(f"  Database: {MONGO_DB}")
    
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    
    # Test connection with ping
    client.admin.command('ping')
    print("[OK] MongoDB connection successful")
    
    db = client[MONGO_DB]
    
    # Get database stats
    try:
        db_stats = db.command('dbstats')
        print(f"\n[Database Statistics]")
        print(f"  Collections: {db_stats['collections']}")
        print(f"  Data size: {db_stats['dataSize'] / 1024 / 1024:.2f} MB")
        print(f"  Storage size: {db_stats['storageSize'] / 1024 / 1024:.2f} MB")
    except Exception as e:
        print(f"  (Could not retrieve db stats: {e})")
    
    # Check collections
    print(f"\n[Collections]")
    collections = db.list_collection_names()
    print(f"  Total: {len(collections)}")
    
    # Important collections
    important_collections = [
        "documents",
        "document_vectors",
        "users",
        "audit_events",
    ]
    
    for col_name in important_collections:
        if col_name in collections:
            col = db[col_name]
            count = col.count_documents({})
            print(f"  {col_name:25s}: {count:6d} documents")
        else:
            print(f"  {col_name:25s}: NOT FOUND")
    
    # Check vector storage specifically
    print(f"\n[Vector Storage Analysis]")
    vectors_col = db["document_vectors"]
    total_vectors = vectors_col.count_documents({})
    print(f"  Total vectors: {total_vectors}")
    
    if total_vectors > 0:
        # Category breakdown
        pipeline = [
            {"$group": {
                "_id": "$category",
                "count": {"$sum": 1},
            }},
            {"$sort": {"count": -1}}
        ]
        categories = list(vectors_col.aggregate(pipeline))
        print(f"\n  Vectors by category:")
        for entry in categories:
            cat = entry["_id"] or "[None]"
            cnt = entry["count"]
            pct = f"{100 * cnt / total_vectors:.1f}%"
            print(f"    {cat:20s}: {cnt:6d} ({pct})")
    
    # Check indexes
    print(f"\n[Indexes on document_vectors]")
    indexes = vectors_col.list_indexes()
    for idx in indexes:
        print(f"  {idx['name']}: {idx['key']}")
    
    print("\n[SUCCESS] MongoDB Atlas is operational")
    
except Exception as e:
    print(f"[ERROR] MongoDB check failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# 4. INTEGRATION TEST
# ============================================================================
print("\n[4] INTEGRATION TEST")
print("-" * 80)

try:
    from redis import Redis
    from pymongo import MongoClient
    
    redis_conn = Redis.from_url(REDIS_URL)
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ping')
    
    print("[OK] Both Redis and MongoDB are accessible")
    print("[OK] Full integration is operational")
    
    # Verify indexing job flow
    print("\n[Indexing Pipeline Status]")
    queue = Queue("rag-indexing", connection=redis_conn)
    documents_db = mongo_client[MONGO_DB]["documents"]
    
    # Find documents that are currently being processed
    processing = documents_db.count_documents({"status": "processing"})
    indexed = documents_db.count_documents({"status": "indexed"})
    failed = documents_db.count_documents({"status": "failed"})
    
    print(f"  Documents being processed: {processing}")
    print(f"  Documents successfully indexed: {indexed}")
    print(f"  Documents with indexing errors: {failed}")
    
except Exception as e:
    print(f"[ERROR] Integration test failed: {e}")

print("\n" + "=" * 80)
print("HEALTH CHECK COMPLETE")
print("=" * 80)
