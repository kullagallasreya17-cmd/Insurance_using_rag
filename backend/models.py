from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UserRecord:
    id: int
    username: str
    full_name: str
    role: str = "agent"
    hashed_password: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentRecord:
    id: int
    filename: str
    stored_path: str
    document_type: str
    category: str
    uploaded_by: str
    status: str = "indexed"
    pages: int = 0
    chunks: int = 0
    word_count: int = 0
    processing_time_seconds: float = 0.0
    version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> "DocumentRecord":
        return cls(
            id=int(data.get("id", 0)),
            filename=data.get("filename", ""),
            stored_path=data.get("stored_path", ""),
            document_type=data.get("document_type", ""),
            category=data.get("category", ""),
            uploaded_by=data.get("uploaded_by", ""),
            status=data.get("status", "indexed"),
            pages=int(data.get("pages", 0) or 0),
            chunks=int(data.get("chunks", 0) or 0),
            word_count=int(data.get("word_count", 0) or 0),
            processing_time_seconds=float(data.get("processing_time_seconds", 0.0) or 0.0),
            version=int(data.get("version", 1) or 1),
            created_at=data.get("created_at") or datetime.utcnow(),
        )

    def to_mongo(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentVersionRecord:
    document_id: int
    version_number: int
    stored_path: str
    filename: str
    created_by: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimAnalysisRecord:
    id: int
    question: str
    decision: str
    confidence: str
    rationale: str
    created_by: str
    missing_information: str = ""
    explanation_trail: Any = ""
    evidence_summary: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditLogRecord:
    actor: str
    actor_role: str
    action: str
    target_type: str = ""
    target_id: str = ""
    details: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict[str, Any]:
        return asdict(self)
