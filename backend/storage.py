import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


BASE_DIR = Path(__file__).resolve().parent
LOCAL_STORAGE_DIR = Path(os.getenv("LOCAL_STORAGE_DIR", str(BASE_DIR / "documents")))
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "insurance-documents").strip("/")


class ObjectStorage:
    def save(self, fileobj: BinaryIO, key: str, content_type: str = "") -> dict:
        raise NotImplementedError

    @contextmanager
    def open_for_read(self, document: dict) -> Iterator[Path]:
        raise NotImplementedError

    def delete(self, document: dict) -> None:
        raise NotImplementedError

    def download_url(self, document: dict) -> str | None:
        return None


class LocalStorage(ObjectStorage):
    def __init__(self, root: Path = LOCAL_STORAGE_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, fileobj: BinaryIO, key: str, content_type: str = "") -> dict:
        destination = self.root / Path(key).name
        with destination.open("wb") as handle:
            while chunk := fileobj.read(1024 * 1024):
                handle.write(chunk)
        return {
            "storage_backend": "local",
            "storage_key": destination.name,
            "stored_path": str(destination),
            "content_type": content_type,
        }

    @contextmanager
    def open_for_read(self, document: dict) -> Iterator[Path]:
        stored_path = Path(document.get("stored_path", ""))
        if not stored_path.exists():
            candidate = self.root / str(document.get("storage_key", ""))
            stored_path = candidate if candidate.exists() else stored_path
        yield stored_path

    def delete(self, document: dict) -> None:
        for value in (document.get("stored_path"), self.root / str(document.get("storage_key", ""))):
            path = Path(value or "")
            if path.exists() and path.is_file():
                path.unlink()


class S3Storage(ObjectStorage):
    def __init__(self):
        if not S3_BUCKET:
            raise RuntimeError("S3_BUCKET must be set when STORAGE_BACKEND=s3")
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3") from exc
        self.bucket = S3_BUCKET
        self.client = boto3.client("s3")

    def _object_key(self, key: str) -> str:
        return f"{S3_PREFIX}/{Path(key).name}" if S3_PREFIX else Path(key).name

    def save(self, fileobj: BinaryIO, key: str, content_type: str = "") -> dict:
        object_key = self._object_key(key)
        extra_args = {"ContentType": content_type} if content_type else None
        if extra_args:
            self.client.upload_fileobj(fileobj, self.bucket, object_key, ExtraArgs=extra_args)
        else:
            self.client.upload_fileobj(fileobj, self.bucket, object_key)
        return {
            "storage_backend": "s3",
            "storage_key": object_key,
            "stored_path": f"s3://{self.bucket}/{object_key}",
            "content_type": content_type,
        }

    @contextmanager
    def open_for_read(self, document: dict) -> Iterator[Path]:
        suffix = Path(document.get("filename", "")).suffix or ".bin"
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = Path(temp.name)
        temp.close()
        try:
            self.client.download_file(self.bucket, document["storage_key"], str(temp_path))
            yield temp_path
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def delete(self, document: dict) -> None:
        key = document.get("storage_key")
        if key:
            self.client.delete_object(Bucket=self.bucket, Key=key)

    def download_url(self, document: dict) -> str | None:
        key = document.get("storage_key")
        if not key:
            return None
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=int(os.getenv("S3_DOWNLOAD_URL_TTL_SECONDS", "300")),
        )


def get_storage() -> ObjectStorage:
    if STORAGE_BACKEND == "s3":
        return S3Storage()
    return LocalStorage()
