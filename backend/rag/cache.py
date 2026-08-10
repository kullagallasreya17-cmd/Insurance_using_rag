import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timedelta

from database import get_database


CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "mongo").lower()
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))


class SimpleCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        path = self.cache_dir / f"{self._key(key)}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        path = self.cache_dir / f"{self._key(key)}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(value, handle)


class MongoCache:
    def _key(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @property
    def collection(self):
        return get_database().rag_cache

    def get(self, key: str) -> Optional[Any]:
        record = self.collection.find_one({"_id": self._key(key), "expires_at": {"$gt": datetime.utcnow()}})
        return record.get("value") if record else None

    def set(self, key: str, value: Any) -> None:
        self.collection.update_one(
            {"_id": self._key(key)},
            {
                "$set": {
                    "value": value,
                    "updated_at": datetime.utcnow(),
                    "expires_at": datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS),
                }
            },
            upsert=True,
        )


cache = SimpleCache() if CACHE_BACKEND == "local" else MongoCache()
