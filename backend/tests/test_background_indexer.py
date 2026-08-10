import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.background_indexer import BackgroundIndexer


def test_background_indexer_processes_enqueued_jobs():
    completed = []
    event = threading.Event()

    def handler(job):
        completed.append(job["payload"])
        event.set()

    indexer = BackgroundIndexer(handler=handler, worker_count=1)
    indexer.start()

    try:
        job_id = indexer.enqueue({"payload": "hello"})
        assert job_id is not None
        assert event.wait(timeout=2)
        assert completed == ["hello"]
    finally:
        indexer.stop()
