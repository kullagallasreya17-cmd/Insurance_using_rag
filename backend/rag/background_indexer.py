import queue
import threading
import uuid
from typing import Callable, Optional


class BackgroundIndexer:
    def __init__(self, handler: Optional[Callable[[dict], None]] = None, worker_count: int = 1):
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._handler = handler or self._default_handler
        self._worker_count = max(1, worker_count)
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._started = False

    def _default_handler(self, job: dict) -> None:
        return None

    def start(self) -> None:
        if self._started:
            return
        for _ in range(self._worker_count):
            thread = threading.Thread(target=self._run, daemon=True)
            thread.start()
            self._threads.append(thread)
        self._started = True

    def stop(self) -> None:
        self._stop_event.set()
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()
        self._started = False

    def enqueue(self, payload: dict) -> str:
        job_id = str(uuid.uuid4())
        self._queue.put({"id": job_id, **payload})
        return job_id

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                break
            try:
                self._handler(job)
            finally:
                self._queue.task_done()
