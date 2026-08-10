import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional

from pymongo import ASCENDING, ReturnDocument


class MongoJobIndexer:
    def __init__(
        self,
        db_provider: Callable[[], object],
        handler: Callable[[dict], None],
        worker_count: int = 1,
        lease_seconds: int = 300,
        poll_seconds: float = 1.0,
    ):
        self._db_provider = db_provider
        self._handler = handler
        self._worker_count = max(1, worker_count)
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._started = False

    def init_indexes(self) -> None:
        jobs = self._db_provider().indexing_jobs
        jobs.create_index([("status", ASCENDING), ("locked_until", ASCENDING), ("created_at", ASCENDING)])
        jobs.create_index("job_id", unique=True)
        jobs.create_index("document_id")

    def start(self) -> None:
        if self._started:
            return
        self.init_indexes()
        self._stop_event.clear()
        for _ in range(self._worker_count):
            thread = threading.Thread(target=self._run, daemon=True)
            thread.start()
            self._threads.append(thread)
        self._started = True

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()
        self._started = False

    def enqueue(self, payload: dict) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        self._db_provider().indexing_jobs.insert_one(
            {
                "job_id": job_id,
                "status": "queued",
                "attempts": 0,
                "payload": payload,
                "document_id": payload.get("document_id"),
                "created_at": now,
                "updated_at": now,
                "locked_until": now,
            }
        )
        return job_id

    def _claim_next_job(self) -> Optional[dict]:
        now = datetime.utcnow()
        return self._db_provider().indexing_jobs.find_one_and_update(
            {
                "status": {"$in": ["queued", "processing"]},
                "locked_until": {"$lte": now},
            },
            {
                "$set": {
                    "status": "processing",
                    "locked_until": now + timedelta(seconds=self._lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )

    def _complete(self, job_id: str) -> None:
        self._db_provider().indexing_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "completed", "updated_at": datetime.utcnow()}},
        )

    def _fail(self, job_id: str, exc: Exception) -> None:
        self._db_provider().indexing_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if not job:
                time.sleep(self._poll_seconds)
                continue
            try:
                self._handler({"id": job["job_id"], **job.get("payload", {})})
                self._complete(job["job_id"])
            except Exception as exc:
                self._fail(job["job_id"], exc)
