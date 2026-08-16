import logging
from typing import Any

from redis import Redis
from rq import Queue


class RQJobIndexer:
    def __init__(self, redis_url: str = "redis://redis:6379/0", queue_name: str = "rag-indexing"):
        self._redis_url = redis_url
        self._queue_name = queue_name
        self._connection = Redis.from_url(redis_url)
        self._queue = Queue(queue_name, connection=self._connection)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def enqueue(self, payload: dict[str, Any]) -> str:
        try:
            job = self._queue.enqueue_call(
                func="main.process_indexing_job",
                args=(payload,),
                timeout=3600,
                result_ttl=0,
                ttl=86400,
            )
            queue_length = len(self._queue)
            logging.info(
                "RQ enqueue: queue=%s redis_url=%s job_id=%s payload_document_id=%s queue_length=%s",
                self._queue_name,
                self._redis_url,
                job.id,
                payload.get("document_id"),
                queue_length,
            )
            return str(job.id)
        except Exception:
            logging.exception("Failed to enqueue RQ job to queue=%s redis_url=%s", self._queue_name, self._redis_url)
            raise
