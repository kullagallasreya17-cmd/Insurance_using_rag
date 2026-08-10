from typing import Any, Callable


class JobQueue:
    def __init__(self, queue_name: str = "rag-indexing"):
        self._queue_name = queue_name
        self._jobs: list[tuple[Callable[..., Any] | str, tuple[Any, ...], dict[str, Any]]] = []

    @property
    def queue(self):
        return self._jobs

    def enqueue(self, func: Callable[..., Any] | str, *args, **kwargs) -> dict[str, Any]:
        job = {"id": str(len(self._jobs) + 1), "func": func, "args": args, "kwargs": kwargs}
        self._jobs.append((func, args, kwargs))
        if callable(func):
            job["result"] = func(*args, **kwargs)
        return job


queue = JobQueue()
