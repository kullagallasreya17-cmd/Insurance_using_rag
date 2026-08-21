import logging
import os
import sys
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import mimetypes
import hashlib
import hmac
import secrets
from datetime import timedelta, timezone

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse

from auth import clear_active_user, create_access_token, get_current_user
from agents.insurance_agent import InsuranceAgent
from claim_engine import _retrieve_claim_context, analyze_claim, build_document_citations
from database import get_database, get_db, init_db, get_next_id, hash_password, verify_password
from rag.background_indexer import BackgroundIndexer
from rag.mongo_indexer import MongoJobIndexer
from rag.rq_indexer import RQJobIndexer
from rag.indexer import extract_document_preview, index_document
from rag.retriever import retrieve_documents
from rag.query_router import ClaimIntent, resolve_claim_intent
from rag.web_search import web_search
from rag.generator import generate_answer
from rag.summarizer import generate_policy_summary
from schemas import (
    ChatRequest,
    ClaimRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    WebSearchRequest,
)
from email_service import send_email
from storage import get_storage


load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
INDEXING_BACKEND = os.getenv("INDEXING_BACKEND", "local").lower()
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LOCAL_INDEXER_WORKERS = int(os.getenv("LOCAL_INDEXER_WORKERS", "2"))
INDEXER_LEASE_SECONDS = int(os.getenv("INDEXER_LEASE_SECONDS", "300"))
ALLOW_LOCAL_INDEXING_FALLBACK = os.getenv("ALLOW_LOCAL_INDEXING_FALLBACK", "true").lower() == "true"
UPLOAD_TYPES = {
    "upload-policy": "policy",
    "upload-report": "medical_report",
    "upload-bill": "hospital_bill",
    "upload-prescription": "prescription",
    "upload-lab-report": "lab_report",
}
CLAIM_EVIDENCE_TYPES = {"medical_report", "hospital_bill", "prescription", "lab_report"}
KNOWLEDGE_CATEGORIES = [
    "health_policy",
    "vehicle_policy",
    "life_policy",
    "home_policy",
    "travel_policy",
    "personal_accident_policy",
    "critical_illness_policy",
    "property_policy",
    "claim_procedure",
    "terms_conditions",
    "faq",
    "medical_document",
    "other",
]

LEGACY_ROLE_ALIASES = {
    "admin": "admin",
    "customer": "customer",
    "auditor": "auditor",
}

ROLE_CATEGORY_ACCESS = {
    "admin": set(KNOWLEDGE_CATEGORIES),
    "customer": set(KNOWLEDGE_CATEGORIES),
    "auditor": set(KNOWLEDGE_CATEGORIES),
}

ROLE_PERMISSIONS = {
    "admin": [
        "documents:upload",
        "documents:read",
        "documents:delete",
        "documents:reindex",
        "chat:ask",
        "claims:analyze",
        "claims:read",
        "dashboard:read",
        "analytics:read",
        "admin:read",
        "audit:read",
        "monitoring:read",
        "users:manage",
        "settings:edit",
    ],
    "customer": [
        "documents:upload",
        "documents:read",
        "chat:ask",
        "claims:analyze",
        "claims:read",
        "dashboard:read",
    ],
    "auditor": [
        "documents:read",
        "claims:read",
        "dashboard:read",
        "analytics:read",
        "audit:read",
        "monitoring:read",
    ],
}

# -------------------------------------------------
# FastAPI App
# -------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    background_indexer.start()
    try:
        yield
    finally:
        background_indexer.stop()


app = FastAPI(
    title="Insurance RAG API",
    description="Insurance RAG + Agentic AI using FastAPI and LangChain",
    version="1.0.0",
    lifespan=lifespan,
)

# -------------------------------------------------
# CORS
# -------------------------------------------------

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Agent
# -------------------------------------------------

agent = InsuranceAgent()
storage = get_storage()


def process_indexing_job(job: dict):
    document_id = job.get("document_id")
    if not document_id:
        logging.warning("Indexing job received without document_id: %s", job)
        return

    db = next(get_db())
    document = db.documents.find_one({"id": document_id})
    if not document:
        logging.warning("Indexing job references missing document_id=%s payload=%s", document_id, job)
        return

    stored_path = document.get("stored_path")
    resolved_path = None
    try:
        db.documents.update_one(
            {"id": document_id},
            {"$set": {"status": "processing", "started_indexing_at": datetime.utcnow()}}
        )

        with storage.open_for_read(document) as file_path:
            resolved_path = Path(file_path) if isinstance(file_path, (str, Path)) else file_path
            logging.info(
                "Indexing document: document_id=%s stored_path=%s resolved_path=%s exists=%s",
                document_id,
                stored_path,
                str(resolved_path) if resolved_path else None,
                bool(resolved_path and resolved_path.exists()),
            )
            if not resolved_path or not resolved_path.exists():
                raise FileNotFoundError(f"Stored document file not found for document_id={document_id}: {stored_path}")

            index_result = index_document(
                resolved_path,
                job.get("document_type", document.get("document_type", "unknown")),
                job.get("category", document.get("category", "unknown")),
                job.get("content_type", document.get("content_type", "application/octet-stream")),
                document_id=document_id,
                filename=job.get("filename", document.get("filename")),
            )

            if job.get("document_type", document.get("document_type")) == "policy":
                db.documents.update_one(
                    {"id": document_id},
                    {"$set": {"summary_status": "generating", "updated_at": datetime.utcnow()}},
                )
                summary_result = generate_policy_summary({**document, **job, "id": document_id})
            else:
                summary_result = None
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logging.error("Indexing failed for document %s: %s", document_id, error_message)
        db.documents.update_one(
            {"id": document_id},
            {"$set": {
                "status": "failed",
                "indexing_error": str(exc),
                "indexing_error_trace": traceback.format_exc(),
                "updated_at": datetime.utcnow(),
            }}
        )
        record_metric_event(
            db,
            "document_indexing",
            status="failed",
            details={"document_id": document_id, "stage": "indexing", "error": str(exc)},
        )
        log_audit_event(
            db,
            actor=job.get("uploaded_by", "system"),
            role="system",
            action="index_document_failed",
            target_type="document",
            target_id=str(document_id),
            details=error_message,
        )
        raise

    final_status = "indexed" if index_result.get("status") in {"indexed", "skipped", "completed"} else "failed"
    update_fields = {
        "status": final_status,
        "pages": index_result.get("pages", 0),
        "chunks": index_result.get("chunks", 0),
        "word_count": index_result.get("word_count", 0),
        "processing_time_seconds": index_result.get("processing_time_seconds", 0),
        "indexed_at": datetime.utcnow(),
        "indexing_error": None,
        "updated_at": datetime.utcnow(),
    }
    if summary_result:
        update_fields.update(
            {
                "policy_summary": summary_result.get("summary"),
                "summary_status": summary_result.get("summary_status"),
                "summary_error": summary_result.get("summary_error"),
                "summary_generated_at": summary_result.get("summary_generated_at"),
            }
        )

    db.documents.update_one(
        {"id": document_id},
        {"$set": update_fields},
    )
    record_metric_event(
        db,
        "document_indexing",
        status="success",
        duration_ms=float(index_result.get("processing_time_seconds", 0) or 0) * 1000,
        details={
            "document_id": document_id,
            "pages": index_result.get("pages", 0),
            "chunks": index_result.get("chunks", 0),
            "chunks_indexed": index_result.get("chunks_indexed", 0),
        },
    )

    log_audit_event(
        db,
        actor=job.get("uploaded_by", "system"),
        role="system",
        action="index_document_completed",
        target_type="document",
        target_id=str(document_id),
        details=f"Indexed {job.get('filename', document.get('filename', 'unknown'))} into {document.get('category', 'unknown')} with status={final_status}",
    )


if INDEXING_BACKEND == "mongo":
    background_indexer = MongoJobIndexer(
        db_provider=get_database,
        handler=process_indexing_job,
        worker_count=LOCAL_INDEXER_WORKERS,
        lease_seconds=INDEXER_LEASE_SECONDS,
    )
elif INDEXING_BACKEND == "rq":
    background_indexer = RQJobIndexer(redis_url=REDIS_URL, queue_name="rag-indexing")
else:
    background_indexer = BackgroundIndexer(handler=process_indexing_job, worker_count=LOCAL_INDEXER_WORKERS)


def _mask_redis_url(redis_url: str | None) -> str:
    if not redis_url:
        return "redis://<not-set>"
    parsed = redis_url.split("@", 1)
    if len(parsed) == 2:
        user_info, host = parsed
        return f"{user_info.split(':', 1)[0]}:***@{host}"
    return redis_url


def enqueue_indexing_job(payload: dict) -> str:
    document_id = payload.get("document_id")
    queue_name = "rag-indexing"
    logging.info(
        "Enqueueing indexing job: document_id=%s queue=%s redis_url=%s payload=%s",
        document_id,
        queue_name,
        _mask_redis_url(REDIS_URL),
        payload,
    )
    job_id = background_indexer.enqueue(payload)
    try:
        from rq import Queue
        from redis import Redis

        queue = Queue(queue_name, connection=Redis.from_url(REDIS_URL))
        logging.info(
            "Queue status after enqueue: document_id=%s queue=%s job_id=%s queue_length=%s",
            document_id,
            queue_name,
            job_id,
            len(queue),
        )
    except Exception:
        logging.exception("Unable to read RQ queue length after enqueue for document_id=%s", document_id)
    return job_id


def normalize_role(role: str | None) -> str:
    return LEGACY_ROLE_ALIASES.get((role or "").lower(), "customer")


def get_accessible_categories(role: str | None):
    return set(ROLE_CATEGORY_ACCESS.get(normalize_role(role), ROLE_CATEGORY_ACCESS["customer"]))


def get_role_permissions(role: str | None) -> list[str]:
    return ROLE_PERMISSIONS.get(normalize_role(role), ROLE_PERMISSIONS["customer"])


def require_permission(current_user: dict, permission: str):
    if permission not in get_role_permissions(current_user.get("role")):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_any_permission(current_user: dict, permissions: list[str]):
    user_permissions = set(get_role_permissions(current_user.get("role")))
    if not user_permissions.intersection(permissions):
        raise HTTPException(status_code=403, detail=f"One of these permissions is required: {', '.join(permissions)}")


def can_view_all_records(current_user: dict) -> bool:
    return normalize_role(current_user.get("role")) in {"admin", "auditor"}


def owner_scoped_query(current_user: dict, owner_field: str = "uploaded_by") -> dict:
    if can_view_all_records(current_user):
        return {}
    return {owner_field: current_user["username"]}


def require_document_access(document: dict | None, current_user: dict, expected_type: str | None = None) -> dict:
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if expected_type and document.get("document_type") != expected_type:
        raise HTTPException(status_code=400, detail=f"Expected a {expected_type} document")
    if not can_view_all_records(current_user) and document.get("uploaded_by") != current_user["username"]:
        raise HTTPException(status_code=403, detail="You can only use your own documents")
    return document


def resolve_claim_documents(db, request: ClaimRequest, current_user: dict) -> tuple[dict | None, list[dict], list[str]]:
    policy_document = None
    if request.policy_document_id is not None:
        policy_document = require_document_access(
            db.documents.find_one({"id": request.policy_document_id}),
            current_user,
            expected_type="policy",
        )

    claim_documents = []
    if request.claim_document_ids:
        found = list(db.documents.find({"id": {"$in": request.claim_document_ids}}))
        found_by_id = {doc.get("id"): doc for doc in found}
        missing_ids = [doc_id for doc_id in request.claim_document_ids if doc_id not in found_by_id]
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Claim document(s) not found: {missing_ids}")
        for doc_id in request.claim_document_ids:
            document = require_document_access(found_by_id[doc_id], current_user)
            if document.get("document_type") == "policy":
                raise HTTPException(status_code=400, detail="Claim document IDs must refer to supporting claim evidence, not policies")
            if document.get("document_type") not in CLAIM_EVIDENCE_TYPES:
                raise HTTPException(status_code=400, detail="Unsupported claim evidence document type")
            claim_documents.append(document)

    inferred_types = list(request.uploaded_document_types or [])
    for document in claim_documents:
        document_type = document.get("document_type")
        if document_type and document_type not in inferred_types:
            inferred_types.append(document_type)
    if policy_document and "policy" not in inferred_types:
        inferred_types.append("policy")

    return policy_document, claim_documents, inferred_types


def format_datetime(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def format_details(value):
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, default=str)
    return value or ""


def normalize_list_field(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def resolve_document_file(document: dict, db):
    with storage.open_for_read(document) as stored_path:
        if stored_path.exists():
            return stored_path
    return None


def log_audit_event(db, actor: str, role: str, action: str, target_type: str = "", target_id: str = "", details: str = ""):
    db.audit_logs.insert_one(
        {
            "id": get_next_id("audit_logs"),
            "actor": actor,
            "actor_role": role,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "created_at": datetime.utcnow(),
        }
    )


def record_metric_event(
    db,
    event_type: str,
    status: str = "success",
    duration_ms: float = 0.0,
    details: dict | None = None,
):
    db.monitoring_events.insert_one(
        {
            "id": get_next_id("monitoring_events"),
            "event_type": event_type,
            "status": status,
            "duration_ms": round(float(duration_ms or 0.0), 2),
            "details": details or {},
            "created_at": datetime.utcnow(),
        }
    )


def get_queue_depth() -> int | None:
    try:
        from rq import Queue
        from redis import Redis

        queue = Queue("rag-indexing", connection=Redis.from_url(REDIS_URL))
        return len(queue)
    except Exception:
        return None


def build_monitoring_snapshot(db):
    documents_uploaded = db.documents.count_documents({})
    documents_indexed = db.documents.count_documents({"status": {"$in": ["indexed", "completed"]}})
    documents_processing = db.documents.count_documents({"status": "processing"})
    failed_documents = db.documents.count_documents({"status": "failed"})
    rag_queries = db.monitoring_events.count_documents({"event_type": {"$in": ["rag_query", "claim_analysis"]}})
    successful_responses = db.monitoring_events.count_documents(
        {"event_type": {"$in": ["rag_query", "claim_analysis"]}, "status": "success"}
    )
    failed_responses = db.monitoring_events.count_documents(
        {"event_type": {"$in": ["rag_query", "claim_analysis"]}, "status": "failed"}
    )

    latency_rows = list(
        db.monitoring_events.aggregate(
            [
                {"$match": {"event_type": {"$in": ["rag_query", "claim_analysis"]}}},
                {
                    "$group": {
                        "_id": "$event_type",
                        "avg_duration_ms": {"$avg": {"$ifNull": ["$duration_ms", 0]}},
                        "count": {"$sum": 1},
                    }
                },
            ]
        )
    )
    latency = {
        row["_id"]: {
            "count": row.get("count", 0),
            "avg_duration_ms": round(float(row.get("avg_duration_ms") or 0), 2),
        }
        for row in latency_rows
    }

    recent_events = list(
        db.monitoring_events.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(10)
    )

    return {
        "documents_uploaded": documents_uploaded,
        "documents_indexed": documents_indexed,
        "documents_processing": documents_processing,
        "failed_documents": failed_documents,
        "rag_queries": rag_queries,
        "successful_responses": successful_responses,
        "failed_responses": failed_responses,
        "api_errors": db.monitoring_events.count_documents({"status": "failed"}),
        "queue_jobs": get_queue_depth(),
        "latency": latency,
        "recent_events": [
            {
                **event,
                "created_at": format_datetime(event.get("created_at")),
            }
            for event in recent_events
        ],
        "pipeline": {
            "upload": "ok" if documents_uploaded else "idle",
            "queue": "ok" if (get_queue_depth() or 0) >= 0 else "unknown",
            "worker": "degraded" if documents_processing and failed_documents else "ok",
            "pdf_processing": "degraded" if failed_documents else "ok",
            "embeddings": "ok" if documents_indexed else "idle",
            "vector_db": "active",
            "llm": "configured" if os.getenv("GOOGLE_API_KEY") else "not_configured",
        },
    }

# -------------------------------------------------
# Routes
# -------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Insurance RAG Backend is Running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "indexing_backend": INDEXING_BACKEND,
        "storage_backend": os.getenv("STORAGE_BACKEND", "local").lower(),
    }


AUTH_TOKEN_TTL_MINUTES = int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "30"))
RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "900"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "3"))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def enforce_auth_rate_limit(request_key: str):
    try:
        from redis import Redis

        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
        key = f"auth-rate:{request_key}"
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        if count > RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    except HTTPException:
        raise
    except Exception:
        logging.warning("Auth rate limiting unavailable")


def request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "unknown")


def issue_email_token(collection, user_id: int, ttl_minutes: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    collection.insert_one({
        "id": get_next_id(collection.name),
        "user_id": user_id,
        "token_hash": token_hash(raw_token),
        "expires_at": now + timedelta(minutes=ttl_minutes),
        "used_at": None,
        "created_at": now,
    })
    return raw_token


def consume_token(collection, raw_token: str):
    token_record = collection.find_one({"token_hash": token_hash(raw_token), "used_at": None})
    if not token_record or token_record.get("expires_at") and token_record["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    updated = collection.find_one_and_update(
        {"_id": token_record["_id"], "used_at": None},
        {"$set": {"used_at": datetime.utcnow()}},
    )
    if not updated:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    return token_record


@app.post("/auth/login")
def login(request: LoginRequest, db = Depends(get_db)):
    requested_role = normalize_role(request.role)
    user = db.users.find_one({"username": request.username})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if requested_role and normalize_role(user.get("role")) != requested_role:
        raise HTTPException(status_code=403, detail=f"This account is not registered as a {requested_role}.")

    if not verify_password(request.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="This account is inactive.")
    if not user.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email address before logging in.")

    token = create_access_token({"sub": user["username"], "role": normalize_role(user.get("role")), "token_version": user.get("token_version", 0)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "role": normalize_role(user.get("role")),
        },
    }


@app.post("/auth/register")
def register(request: RegisterRequest, db = Depends(get_db)):
    existing_user = db.users.find_one({"$or": [{"username": request.username}, {"email": request.email}]})
    if existing_user:
        raise HTTPException(status_code=409, detail="An account with these details already exists.")

    user_id = get_next_id("users")
    user = {
        "id": user_id,
        "username": request.username,
        "full_name": request.full_name,
        # Public registration cannot grant elevated admin or auditor access.
        "role": request.role,
        "hashed_password": hash_password(request.password),
        "password_hash": hash_password(request.password),
        "email": request.email,
        "is_active": True,
        "email_verified": False,
        "token_version": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    db.users.insert_one(user)
    raw_token = issue_email_token(db.email_verification_tokens, user_id, AUTH_TOKEN_TTL_MINUTES)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    try:
        send_email(
            user["email"],
            "Verify your Insurance AI Platform email",
            f"Hello,\n\nVerify your email: {frontend_url}/verify-email?token={raw_token}\n\nThis link expires shortly.",
        )
    except Exception as exc:
        logging.error("Verification email could not be sent: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Account created, but verification email delivery is unavailable.") from exc
    return {
        "message": "Account created. Please verify your email address before logging in.",
    }


@app.post("/auth/verify-email")
def verify_email(request: TokenRequest, db = Depends(get_db)):
    token_record = consume_token(db.email_verification_tokens, request.token)
    user = db.users.find_one({"id": token_record["user_id"]})
    if not user:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    db.users.update_one({"id": user["id"]}, {"$set": {"email_verified": True, "updated_at": datetime.utcnow()}})
    return {"message": "Your email has been verified successfully."}


@app.post("/auth/resend-verification")
def resend_verification(request: ForgotPasswordRequest, http_request: Request, db = Depends(get_db)):
    enforce_auth_rate_limit(f"email:{request.email.strip().lower()}")
    enforce_auth_rate_limit(f"ip:{request_ip(http_request)}")
    user = db.users.find_one({"email": request.email.strip().lower()})
    if user and not user.get("email_verified", False):
        raw_token = issue_email_token(db.email_verification_tokens, user["id"], AUTH_TOKEN_TTL_MINUTES)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
        try:
            send_email(user["email"], "Verify your Insurance AI Platform email", f"Verify your email: {frontend_url}/verify-email?token={raw_token}")
        except Exception:
            logging.exception("Verification email resend failed")
    return {"message": "If an account requires verification, instructions have been sent."}


@app.post("/auth/forgot-password")
def forgot_password(request: ForgotPasswordRequest, http_request: Request, db = Depends(get_db)):
    enforce_auth_rate_limit(f"email:{request.email.strip().lower()}")
    enforce_auth_rate_limit(f"ip:{request_ip(http_request)}")
    user = db.users.find_one({"email": request.email.strip().lower()})
    if user and user.get("is_active", True):
        raw_token = issue_email_token(db.password_reset_tokens, user["id"], RESET_TOKEN_TTL_MINUTES)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
        try:
            send_email(user["email"], "Reset your Insurance AI Platform password", f"Hello,\n\nWe received a request to reset your password.\n\nReset your password: {frontend_url}/reset-password?token={raw_token}\n\nThis link expires shortly and can only be used once.\n\nIf you did not request this, you can safely ignore this email.")
        except Exception:
            logging.exception("Password reset email failed")
    return {"message": "If an account exists for this email, password reset instructions have been sent."}


@app.post("/auth/reset-password")
def reset_password(request: ResetPasswordRequest, db = Depends(get_db)):
    if not hmac.compare_digest(request.password, request.confirm_password):
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    token_record = consume_token(db.password_reset_tokens, request.token)
    user = db.users.find_one({"id": token_record["user_id"]})
    if not user:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")
    password_hash = hash_password(request.password)
    db.users.update_one({"id": user["id"]}, {"$set": {"hashed_password": password_hash, "password_hash": password_hash, "updated_at": datetime.utcnow()}, "$inc": {"token_version": 1}})
    db.active_users.delete_many({"username": user["username"]})
    return {"message": "Your password has been reset successfully."}


@app.post("/auth/logout")
def logout(db = Depends(get_db), current_user = Depends(get_current_user)):
    clear_active_user(current_user["username"], db)
    return {"message": f"{current_user['username']} logged out successfully"}


@app.get("/me")
def me(current_user = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "full_name": current_user.get("full_name"),
        "role": normalize_role(current_user.get("role")),
    }


def serialize_document(document: dict) -> dict:
    return {
        "id": document.get("id"),
        "filename": document.get("filename"),
        "document_type": document.get("document_type"),
        "category": document.get("category"),
        "status": document.get("status"),
        "pages": document.get("pages", 0) or 0,
        "chunks": document.get("chunks", 0) or 0,
        "word_count": document.get("word_count", 0) or 0,
        "processing_time_seconds": document.get("processing_time_seconds", 0) or 0,
        "version": document.get("version", 1),
        "uploaded_by": document.get("uploaded_by"),
        "storage_backend": document.get("storage_backend", "local"),
        "policy_summary": document.get("policy_summary", ""),
        "summary_status": document.get("summary_status"),
        "summary_error": document.get("summary_error"),
        "summary_generated_at": format_datetime(document.get("summary_generated_at")),
        "created_at": format_datetime(document.get("created_at")),
    }


def serialize_claim_analysis(claim: dict, include_sources: bool = False) -> dict:
    data = {
        "id": claim.get("id"),
        "question": claim.get("question"),
        "decision": claim.get("decision"),
        "confidence": claim.get("confidence"),
        "rationale": claim.get("rationale"),
        "missing_information": normalize_list_field(claim.get("missing_information")),
        "explanation_trail": normalize_list_field(claim.get("explanation_trail")),
        "evidence_summary": claim.get("evidence_summary"),
        "document_checklist": claim.get("document_checklist", {}),
        "rag_evaluation": claim.get("rag_evaluation", {}),
        "policy_document_id": claim.get("policy_document_id"),
        "claim_document_ids": claim.get("claim_document_ids", []),
        "analysis_type": claim.get("analysis_type", "claim_analysis"),
        "intent": claim.get("intent", "CLAIM_ANALYSIS_QUERY"),
        "hospital_name": claim.get("hospital_name"),
        "claim_amount": claim.get("claim_amount"),
        "admission_date": claim.get("admission_date"),
        "discharge_date": claim.get("discharge_date"),
        "web_search_used": claim.get("web_search_used", False),
        "created_by": claim.get("created_by"),
        "created_at": format_datetime(claim.get("created_at")),
    }
    if include_sources:
        data["sources"] = claim.get("sources", [])
    return data


@app.get("/profile")
def profile(
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    documents_uploaded = db.documents.count_documents({"uploaded_by": current_user["username"]})
    claims_created = db.claim_analyses.count_documents({"created_by": current_user["username"]})
    return {
        "user": {
            "username": current_user["username"],
            "full_name": current_user.get("full_name"),
            "role": normalize_role(current_user.get("role")),
            "created_at": format_datetime(current_user.get("created_at")),
        },
        "activity": {
            "documents_uploaded": documents_uploaded,
            "claims_created": claims_created,
        },
        "permissions": get_role_permissions(current_user.get("role")),
    }


@app.get("/knowledge-categories")
def knowledge_categories(current_user = Depends(get_current_user)):
    accessible = get_accessible_categories(current_user.get("role"))
    return {"categories": sorted(accessible)}


@app.get("/documents")
def list_documents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:read")
    accessible = get_accessible_categories(current_user.get("role"))
    query = owner_scoped_query(current_user)
    if accessible:
        query["category"] = {"$in": list(accessible)}
    total = db.documents.count_documents(query)
    documents = list(db.documents.find(query).sort("created_at", -1).skip(offset).limit(limit))
    return {
        "documents": [serialize_document(doc) for doc in documents],
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }


@app.get("/upload-history")
def upload_history(
    document_type: str | None = None,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:read")
    accessible = get_accessible_categories(current_user.get("role", "agent"))
    query: dict = {"uploaded_by": current_user["username"]}
    if accessible is not None:
        query["category"] = {"$in": list(accessible)}
    if document_type:
        query["document_type"] = document_type

    documents = list(db.documents.find(query).sort("created_at", -1).limit(10))
    return {"documents": [serialize_document(doc) for doc in documents]}


@app.get("/document/{document_id}/download")
def download_document(
    document_id: int,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:read")
    document = db.documents.find_one({"id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_view_all_records(current_user) and document.get("uploaded_by") != current_user["username"]:
        raise HTTPException(status_code=403, detail="You can only access your own documents")

    download_url = storage.download_url(document)
    if download_url:
        return RedirectResponse(download_url)

    with storage.open_for_read(document) as stored_path:
        if not stored_path or not stored_path.exists():
            raise HTTPException(status_code=404, detail="Stored document file not found")

        media_type, _ = mimetypes.guess_type(stored_path.name)
        if not media_type:
            media_type = "application/octet-stream"

        return FileResponse(
            path=stored_path,
            filename=document.get("filename"),
            media_type=media_type,
        )


@app.delete("/document/{document_id}")
def delete_document(
    document_id: int,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:delete")
    document = db.documents.find_one({"id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    storage.delete(document)

    db.documents.delete_one({"id": document_id})
    db.document_versions.delete_many({"document_id": document_id})
    return {"message": "Document metadata deleted", "id": document_id}


@app.get("/policies")
def policies(
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:read")
    query = {"document_type": "policy", **owner_scoped_query(current_user)}
    policy_docs = list(db.documents.find(query).sort("created_at", -1).limit(200))
    return {
        "policies": [
            {
                "id": doc.get("id"),
                "name": doc.get("filename"),
                "category": doc.get("category"),
                "status": doc.get("status"),
                "pages": doc.get("pages", 0) or 0,
                "chunks": doc.get("chunks", 0) or 0,
                "word_count": doc.get("word_count", 0) or 0,
                "version": doc.get("version", 1),
                "uploaded_by": doc.get("uploaded_by"),
                "stored_path": doc.get("stored_path"),
                "policy_summary": doc.get("policy_summary", ""),
                "summary_status": doc.get("summary_status"),
                "summary_error": doc.get("summary_error"),
                "summary_generated_at": format_datetime(doc.get("summary_generated_at")),
                "created_at": format_datetime(doc.get("created_at")),
            }
            for doc in policy_docs
        ]
    }


@app.get("/dashboard")
def dashboard(
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "dashboard:read")
    document_scope = owner_scoped_query(current_user)
    claim_scope = owner_scoped_query(current_user, owner_field="created_by")

    total_documents = db.documents.count_documents(document_scope)
    policies = db.documents.count_documents({**document_scope, "document_type": "policy"})
    reports = db.documents.count_documents({**document_scope, "document_type": {"$ne": "policy"}})
    claims = db.claim_analyses.count_documents(claim_scope)

    claim_rows = list(
        db.claim_analyses.find(
            claim_scope,
            {"id": 1, "decision": 1, "confidence": 1, "created_at": 1, "_id": 0},
        ).sort("created_at", -1)
    )
    claim_records = [
        type("CR", (), row)
        for row in claim_rows
    ]

    approved_claims = sum(
        1 for claim in claim_records if (getattr(claim, "decision", "") or "").lower() == "approved"
    )
    rejected_claims = sum(
        1 for claim in claim_records if (getattr(claim, "decision", "") or "").lower() == "rejected"
    )
    pending_claims = sum(
        1
        for claim in claim_records
        if (getattr(claim, "decision", "") or "").lower() in {"pending", "needs_review", "review_required"}
    )
    users = db.users.count_documents({})

    recent_documents_rows = list(
        db.documents.find(
            document_scope,
            {"id": 1, "filename": 1, "category": 1, "status": 1, "created_at": 1, "_id": 0},
        ).sort("created_at", -1).limit(5)
    )
    recent_documents = [
        {
            "id": row.get("id"),
            "filename": row.get("filename"),
            "category": row.get("category"),
            "status": row.get("status"),
            "created_at": format_datetime(row.get("created_at")),
        }
        for row in recent_documents_rows
    ]

    recent_claims_rows = list(
        db.claim_analyses.find(
            claim_scope,
            {"id": 1, "decision": 1, "confidence": 1, "created_at": 1, "_id": 0},
        ).sort("created_at", -1).limit(5)
    )
    recent_claims = [
        {
            "id": row.get("id"),
            "decision": row.get("decision"),
            "confidence": row.get("confidence"),
            "created_at": format_datetime(row.get("created_at")),
        }
        for row in recent_claims_rows
    ]

    total_chunks_agg = list(db.documents.aggregate([
        {"$match": document_scope},
        {"$group": {"_id": None, "total_chunks": {"$sum": {"$ifNull": ["$chunks", 0]}}}},
    ]))
    total_chunks = int(total_chunks_agg[0]["total_chunks"] or 0) if total_chunks_agg else 0

    avg_indexing_time_agg = list(db.documents.aggregate([
        {"$match": document_scope},
        {"$group": {"_id": None, "avg_indexing_time": {"$avg": {"$ifNull": ["$processing_time_seconds", 0]}}}},
    ]))
    avg_indexing_time = float(avg_indexing_time_agg[0]["avg_indexing_time"] or 0.0) if avg_indexing_time_agg else 0.0

    return {
        "metrics": {
            "documents": total_documents,
            "policies": policies,
            "reports": reports,
            "claims": claims,
            "approved_claims": approved_claims,
            "rejected_claims": rejected_claims,
            "pending_claims": pending_claims,
            "users": users,
        },
        "ai_statistics": {
            "analyses_completed": claims,
            "high_confidence": sum(
                1 for claim in claim_records if (getattr(claim, "confidence", "") or "").lower() == "high"
            ),
            "medium_confidence": sum(
                1 for claim in claim_records if (getattr(claim, "confidence", "") or "").lower() == "medium"
            ),
            "low_confidence": sum(
                1 for claim in claim_records if (getattr(claim, "confidence", "") or "").lower() == "low"
            ),
            "documents_indexed": total_documents,
            "chunks_indexed": total_chunks,
        },
        "rag_metrics": {
            "avg_indexing_time_seconds": round(avg_indexing_time, 2),
            "total_chunks_indexed": total_chunks,
            "throughput_docs_per_minute": round((total_documents / max(avg_indexing_time * 60, 1)) if avg_indexing_time > 0 else 0.0, 2),
        },
        "system": {
            "backend": "running",
            "api": "connected",
            "vector_db": "active",
            "llm": "configured",
            "database": "connected",
        },
        "monitoring": (
            build_monitoring_snapshot(db)
            if "monitoring:read" in get_role_permissions(current_user.get("role"))
            else None
        ),
        "recent_documents": recent_documents,
        "recent_claims": recent_claims,
    }


@app.get("/analytics")
def analytics(
    db = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    require_permission(current_user, "analytics:read")
    categories = {
        row["_id"] or "unknown": row["count"]
        for row in db.documents.aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}])
    }
    document_types = {
        row["_id"] or "unknown": row["count"]
        for row in db.documents.aggregate([{"$group": {"_id": "$document_type", "count": {"$sum": 1}}}])
    }
    decisions = {
        row["_id"] or "unknown": row["count"]
        for row in db.claim_analyses.aggregate([{"$group": {"_id": "$decision", "count": {"$sum": 1}}}])
    }

    doc_metrics = list(
        db.documents.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "documents": {"$sum": 1},
                        "total_processing_time": {"$sum": {"$ifNull": ["$processing_time_seconds", 0]}},
                        "total_chunks": {"$sum": {"$ifNull": ["$chunks", 0]}},
                    }
                }
            ]
        )
    )
    metrics = doc_metrics[0] if doc_metrics else {"documents": 0, "total_processing_time": 0, "total_chunks": 0}
    total_documents = int(metrics.get("documents", 0) or 0)
    total_processing_time = float(metrics.get("total_processing_time", 0) or 0)
    total_chunks = int(metrics.get("total_chunks", 0) or 0)
    total_claims = db.claim_analyses.count_documents({})
    avg_indexing_time = round(total_processing_time / total_documents, 2) if total_documents else 0.0
    avg_chunks_per_document = round(total_chunks / total_documents, 2) if total_documents else 0.0

    question_counts = {}
    try:
        ask_logs = db.audit_logs.find({"action": "ask_chat"}, {"details": 1, "_id": 0}).sort("created_at", -1).limit(1000)
        for log in ask_logs:
            details = log.get("details")
            if not details:
                continue
            if isinstance(details, dict):
                question = str(details.get("query") or "").strip()
            elif isinstance(details, str) and details.startswith("Asked:"):
                question = details.split("Asked:", 1)[1].strip()
            else:
                question = str(details).strip()
            if not question:
                continue
            question_counts[question] = question_counts.get(question, 0) + 1
    except Exception:
        question_counts = {}

    top_questions = [
        {"question": question, "count": count}
        for question, count in sorted(question_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    return {
        "documents_by_category": categories,
        "documents_by_type": document_types,
        "claims_by_decision": decisions,
        "totals": {
            "documents": total_documents,
            "chunks": total_chunks,
            "claims": total_claims,
        },
        "operational_metrics": {
            "avg_indexing_time_seconds": avg_indexing_time,
            "avg_chunks_per_document": avg_chunks_per_document,
            "throughput_docs_per_minute": round((total_documents / max(total_processing_time, 1)) * 60, 2) if total_processing_time > 0 else 0.0,
            "total_processing_time_seconds": round(total_processing_time, 2),
        },
        "most_asked_questions": top_questions,
    }


@app.get("/notifications")
def notifications(
    db = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    recent_documents = list(db.documents.find(owner_scoped_query(current_user)).sort("created_at", -1).limit(5))
    recent_claims = list(db.claim_analyses.find(owner_scoped_query(current_user, owner_field="created_by")).sort("created_at", -1).limit(5))
    items = [
        {
            "id": f"document-{doc.get('id')}",
            "type": "document",
            "message": f"{doc.get('filename')} indexed as {doc.get('category')}",
            "created_at": format_datetime(doc.get("created_at")),
        }
        for doc in recent_documents
    ]
    items.extend(
        {
            "id": f"claim-{claim.get('id')}",
            "type": "claim",
            "message": f"Claim analysis marked {claim.get('decision')} with {claim.get('confidence')} confidence",
            "created_at": format_datetime(claim.get("created_at")),
        }
        for claim in recent_claims
    )
    return {"notifications": sorted(items, key=lambda item: item["created_at"], reverse=True)}


@app.get("/settings")
def settings(current_user = Depends(get_current_user)):
    require_permission(current_user, "settings:edit")
    return {
        "security": {
            "authentication": "JWT",
            "rbac": "role based",
            "password_hashing": "PBKDF2-SHA256",
            "cors": "enabled for development",
        },
        "rag": {
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2 (Hugging Face)",
            "vector_database": "MongoDB Atlas Vector Search",
            "indexing_backend": INDEXING_BACKEND,
            "storage_backend": os.getenv("STORAGE_BACKEND", "local").lower(),
            "top_k": 6,
            "grounding": "answers require retrieved context",
            "semantic_search": "enabled",
        },
        "limits": {
            "max_file_size_mb": 20,
            "allowed_file_types": ["pdf", "png", "jpg", "jpeg"],
        },
    }


@app.get("/admin/overview")
def admin_overview(
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_any_permission(current_user, ["admin:read", "audit:read", "monitoring:read"])
    is_admin = normalize_role(current_user.get("role")) == "admin"

    users = list(db.users.find({}, {"_id": 0}).sort("created_at", -1).limit(50)) if is_admin else []
    audit_logs = list(db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(10))
    monitoring = build_monitoring_snapshot(db)
    return {
        "monitoring": monitoring,
        "can_manage_users": is_admin,
        "users": [
            {
                "id": user.get("id"),
                "username": user.get("username"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
                "created_at": format_datetime(user.get("created_at")),
            }
            for user in users
        ],
        "audit_logs": [
            {
                "id": log.get("id"),
                "actor": log.get("actor"),
                "actor_role": log.get("actor_role"),
                "action": log.get("action"),
                "details": format_details(log.get("details")),
                "created_at": format_datetime(log.get("created_at")),
            }
            for log in audit_logs
        ],
        "service_health": [
            {"service": "API Gateway", "status": "planned"},
            {"service": "Authentication Service", "status": "running in FastAPI module"},
            {"service": "Document Service", "status": "running in FastAPI module"},
            {"service": "RAG Service", "status": "running in FastAPI module"},
            {"service": "Chat Service", "status": "running in FastAPI module"},
            {"service": "Claim Service", "status": "running in FastAPI module"},
            {"service": "Notification Service", "status": "derived from events"},
        ],
    }


@app.get("/admin/monitoring")
def admin_monitoring(
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "monitoring:read")
    return build_monitoring_snapshot(db)


@app.get("/admin/audit-logs")
def admin_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "audit:read")
    total = db.audit_logs.count_documents({})
    logs = list(db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit))
    return {
        "logs": [
            {
                **log,
                "details": format_details(log.get("details")),
                "created_at": format_datetime(log.get("created_at")),
            }
            for log in logs
        ],
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }


@app.get("/claims")
def list_claims(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "claims:read")
    query = owner_scoped_query(current_user, owner_field="created_by")
    total = db.claim_analyses.count_documents(query)
    claims = list(db.claim_analyses.find(query).sort("created_at", -1).skip(offset).limit(limit))
    return {
        "claims": [
            serialize_claim_analysis(claim)
            for claim in claims
        ],
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }


@app.get("/claim/{claim_id}")
def get_claim(
    claim_id: int,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "claims:read")
    claim = db.claim_analyses.find_one({"id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not can_view_all_records(current_user) and claim.get("created_by") != current_user["username"]:
        raise HTTPException(status_code=403, detail="You can only access your own claims")

    return serialize_claim_analysis(claim, include_sources=True)


@app.post("/chat")
def chat(request: ChatRequest, db = Depends(get_db), current_user = Depends(get_current_user)):
    require_permission(current_user, "chat:ask")
    started_at = time.perf_counter()

    try:

        result = agent.ask_with_metrics(request.question)
        duration_ms = (time.perf_counter() - started_at) * 1000
        record_metric_event(
            db,
            "rag_query",
            status="success" if not result.get("error") else "failed",
            duration_ms=duration_ms,
            details={
                "retrieval_ms": result.get("retrieval_ms", 0),
                "generation_ms": result.get("generation_ms", 0),
                "confidence": result.get("confidence", "medium"),
                "grounding_score": result.get("grounding_score", 0),
                "grounded": result.get("grounded", False),
                "citation_valid": result.get("citation_valid", False),
                "source_count": len(result.get("sources", [])),
                "route": result.get("route"),
                "web_search_used": result.get("web_search_used", False),
                "web_result_count": len(result.get("web_sources", [])),
                "web_provider": result.get("web_provider"),
                "web_search_ok": result.get("web_search_ok", False),
            },
        )
        log_audit_event(
            db,
            actor=current_user["username"],
            role=current_user.get("role", "agent"),
            action="ask_chat",
            target_type="chat",
            target_id="",
            details={
                "query": request.question[:500],
                "retrieved_sections": result.get("sources", []),
                "confidence": result.get("confidence", "medium"),
                "route": result.get("route"),
                "web_search_used": result.get("web_search_used", False),
                "web_result_count": len(result.get("web_sources", [])),
            },
        )

        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "citations": result.get("citations", result.get("sources", [])),
            "confidence": result.get("confidence", "medium"),
            "grounding_score": result.get("grounding_score", 0),
            "grounded": result.get("grounded", False),
            "unsupported_claims": result.get("unsupported_claims", []),
            "citation_valid": result.get("citation_valid", False),
            "retrieval_ms": result.get("retrieval_ms", 0),
            "generation_ms": result.get("generation_ms", 0),
            "route": result.get("route", "POLICY_ONLY"),
            "web_search_used": result.get("web_search_used", False),
            "web_search_ok": result.get("web_search_ok", False),
            "web_search_error": result.get("web_search_error"),
            "web_provider": result.get("web_provider"),
            "web_sources": result.get("web_sources", []),
        }

    except Exception as e:
        record_metric_event(
            db,
            "rag_query",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            details={"error": str(e)},
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/api/search")
def api_search(request: WebSearchRequest, current_user = Depends(get_current_user)):
    require_permission(current_user, "chat:ask")
    result = web_search(request.query, max_results=request.max_results)
    return {"query": request.query, **result}


@app.post("/debug/retrieve")
def debug_retrieve(request: ChatRequest, current_user = Depends(get_current_user)):
    require_permission(current_user, "admin:read")
    try:
        documents = retrieve_documents(request.question)
        return {
            "question": request.question,
            "chunks": [
                {
                    "content": doc.page_content[:1000],
                    "metadata": doc.metadata,
                }
                for doc in documents
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/llm")
def debug_llm():
    """Lightweight LLM health check: attempts to instantiate the configured LLM client."""
    try:
        from rag.generator import _build_llm
        import os

        if not os.getenv("GOOGLE_API_KEY"):
            return {"configured": False, "reason": "GOOGLE_API_KEY is not set"}

        try:
            llm = _build_llm(temperature=0.0)
            # Do not invoke the model here to avoid consuming quota — just return success on instantiation.
            return {"configured": True, "model": os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")}
        except Exception as exc:
            return {"configured": False, "reason": str(exc)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/document/{document_id}/reindex")
def reindex_document(
    document_id: int,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:reindex")
    document = db.documents.find_one({"id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    with storage.open_for_read(document) as file_path:
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="Stored document file not found")

        index_result = index_document(
            file_path,
            document.get("document_type"),
            document.get("category"),
            document.get("content_type") or ("application/pdf" if file_path.suffix.lower() == ".pdf" else "application/octet-stream"),
            document_id=document_id,
            filename=document.get("filename"),
        )
        summary_result = (
            generate_policy_summary(document)
            if document.get("document_type") == "policy"
            else None
        )
    update_fields = {
        "status": "indexed",
        "pages": index_result.get("pages", 0),
        "chunks": index_result.get("chunks", 0),
        "word_count": index_result.get("word_count", 0),
        "processing_time_seconds": index_result.get("processing_time_seconds", 0),
        "updated_at": datetime.utcnow(),
    }
    if summary_result:
        update_fields.update(
            {
                "policy_summary": summary_result.get("summary"),
                "summary_status": summary_result.get("summary_status"),
                "summary_error": summary_result.get("summary_error"),
                "summary_generated_at": summary_result.get("summary_generated_at"),
            }
        )
    db.documents.update_one(
        {"id": document_id},
        {"$set": update_fields},
    )

    return {
        "message": "Document re-indexed successfully.",
        "pages": index_result["pages"],
        "chunks": index_result["chunks"],
        "word_count": index_result.get("word_count", 0),
        "processing_time_seconds": index_result.get("processing_time_seconds", 0),
        "policy_summary": summary_result.get("summary") if summary_result else "",
        "summary_status": summary_result.get("summary_status") if summary_result else None,
    }


@app.post("/document/{document_id}/summary")
def regenerate_policy_summary(
    document_id: int,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:reindex")
    document = db.documents.find_one({"id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.get("document_type") != "policy":
        raise HTTPException(status_code=400, detail="Automatic summaries are available for policy documents only.")

    db.documents.update_one(
        {"id": document_id},
        {"$set": {"summary_status": "generating", "updated_at": datetime.utcnow()}},
    )
    summary_result = generate_policy_summary(document)
    db.documents.update_one(
        {"id": document_id},
        {
            "$set": {
                "policy_summary": summary_result.get("summary"),
                "summary_status": summary_result.get("summary_status"),
                "summary_error": summary_result.get("summary_error"),
                "summary_generated_at": summary_result.get("summary_generated_at"),
                "updated_at": datetime.utcnow(),
            }
        },
    )
    return {
        "document_id": document_id,
        "policy_summary": summary_result.get("summary"),
        "summary_status": summary_result.get("summary_status"),
        "summary_error": summary_result.get("summary_error"),
        "summary_generated_at": format_datetime(summary_result.get("summary_generated_at")),
    }


@app.post("/claim/analyze")
def claim_analyze(
    request: ClaimRequest,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "claims:analyze")
    started_at = time.perf_counter()
    try:
        requested_mode = ((request.mode if request.mode != "auto" else request.analysis_mode) or request.mode or "auto").strip().lower()
        if requested_mode not in {"auto", "policy", "web", "claim"}:
            raise HTTPException(status_code=400, detail="mode must be auto, policy, web, or claim")

        # Manual page modes are authoritative. Only AUTO requests classify intent.
        intent = resolve_claim_intent(
            requested_mode,
            request.question or request.treatment_details or request.diagnosis,
            has_claim_documents=bool(request.claim_document_ids),
        )

        question = request.question or request.treatment_details or request.diagnosis or "claim coverage assessment"
        if intent in {ClaimIntent.POLICY_QUERY, ClaimIntent.MEDICAL_DOCUMENT_QUERY} and requested_mode != "claim":
            policy_document = None
            policy_documents = []
            if request.policy_document_id is not None:
                policy_document = require_document_access(
                    db.documents.find_one({"id": request.policy_document_id}),
                    current_user,
                    expected_type="policy",
                )
            policy_documents, _policy_results = _retrieve_claim_context(
                question,
                policy_category=request.policy_category or (policy_document or {}).get("category") or "health_policy",
                policy_document_id=(policy_document or {}).get("id"),
            )
            logging.info(
                "[POLICY RAG] mode=%s selected_policy_id=%s selected_policy_filename=%s document_type_filter=policy retrieved_chunks=%s",
                requested_mode,
                (policy_document or {}).get("id"),
                (policy_document or {}).get("filename"),
                len(policy_documents),
            )
            result = {
                "answer": generate_answer(question, policy_documents, route="POLICY_ONLY") if policy_documents else "I couldn't find sufficiently relevant information in the selected policy.",
                "confidence": "medium" if policy_documents else "low",
                "sources": build_document_citations(policy_documents),
                "route": "POLICY_ONLY",
            }
            return {
                "mode": requested_mode,
                "response_type": "policy_answer" if intent == ClaimIntent.POLICY_QUERY else "document_answer",
                "analysis_type": "policy_question" if intent == ClaimIntent.POLICY_QUERY else "document_question",
                "intent": intent.value,
                "question": question,
                "answer": result.get("answer", ""),
                "confidence": result.get("confidence", "medium"),
                "sources": result.get("sources", []),
                "route": result.get("route", "POLICY_ONLY"),
                "web_search_used": False,
                "web_search_ok": False,
                "web_sources": [],
            }

        if intent in {ClaimIntent.WEB_QUERY, ClaimIntent.HOSPITAL_COST_QUERY} and requested_mode != "claim":
            web_result = web_search(question)
            return {
                "mode": requested_mode,
                "response_type": "web_answer",
                "analysis_type": "web_question",
                "intent": intent.value,
                "question": question,
                "answer": "Current external information retrieved from the sources below." if web_result.get("results") else "Web information could not be retrieved.",
                "confidence": "medium" if web_result.get("results") else "low",
                "sources": [],
                "web_search_used": True,
                "web_search_ok": web_result.get("ok", False),
                "web_search_error": web_result.get("error"),
                "web_provider": web_result.get("provider"),
                "web_sources": web_result.get("results", []),
                "cost_comparison": web_result.get("results", []) if intent == ClaimIntent.HOSPITAL_COST_QUERY else [],
            }

        policy_document, claim_documents, uploaded_document_types = resolve_claim_documents(
            db,
            request,
            current_user,
        )
        structured_question = request.question or request.treatment_details or request.diagnosis or "claim coverage assessment"
        if request.treatment_details:
            structured_question = f"{request.treatment_details}. Diagnosis: {request.diagnosis or 'not provided'}. Hospital: {request.hospital_name or 'not provided'}. Admission date: {request.admission_date or 'not provided'}. Discharge date: {request.discharge_date or 'not provided'}."

        result = analyze_claim(
            question=structured_question,
            claim_amount=request.claim_amount or request.bill_amount,
            policy_category=request.policy_category or (policy_document or {}).get("category"),
            policy_document_id=(policy_document or {}).get("id"),
            claim_document_ids=[document.get("id") for document in claim_documents],
            uploaded_document_types=uploaded_document_types,
            hospital_name=request.hospital_name,
            hospital_location=request.hospital_location,
            enable_web_search=request.enable_web_search and requested_mode != "claim",
            force_web_research=intent == ClaimIntent.MIXED_CLAIM_QUERY,
        )
        result["mode"] = requested_mode
        result["response_type"] = "claim_analysis"
        result["web_search_used"] = bool(result.get("hospital_research", {}).get("sources"))
        logging.info(
            "[CLAIM] selected_policy_id=%s selected_policy_filename=%s policy_category=%s",
            (policy_document or {}).get("id"),
            (policy_document or {}).get("filename"),
            request.policy_category or (policy_document or {}).get("category"),
        )
        logging.info(
            "[CLAIM ANALYSIS] policy_evidence_count=%s claim_evidence_count=%s decision=%s",
            result.get("rag_evaluation", {}).get("policy_source_count", 0),
            result.get("rag_evaluation", {}).get("claim_source_count", 0),
            result.get("decision"),
        )

        evidence_summary = "; ".join(result.get("covered_items", []) + result.get("exclusions", [])) or "No structured evidence extracted"
        record = {
            "id": get_next_id("claim_analyses"),
            "question": structured_question,
            "decision": result["decision"],
            "confidence": result["confidence"],
            "rationale": result["rationale"],
            "missing_information": result.get("missing_information", []),
            "explanation_trail": result.get("next_steps", []),
            "evidence_summary": evidence_summary,
            "sources": result.get("sources", []),
            "document_checklist": result.get("document_checklist", {}),
            "rag_evaluation": result.get("rag_evaluation", {}),
            "policy_document_id": (policy_document or {}).get("id"),
            "claim_document_ids": [document.get("id") for document in claim_documents],
            "created_by": current_user["username"],
            "created_at": datetime.utcnow(),
            "analysis_type": "claim_analysis",
            "intent": intent.value,
            "hospital_name": request.hospital_name,
            "claim_amount": request.claim_amount or request.bill_amount,
            "admission_date": request.admission_date,
            "discharge_date": request.discharge_date,
            "web_search_used": bool(result.get("hospital_research", {}).get("sources")),
        }
        db.claim_analyses.insert_one(record)
        record_metric_event(
            db,
            "claim_analysis",
            status="success",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            details={
                "claim_id": record["id"],
                "decision": result.get("decision"),
                "confidence": result.get("confidence"),
                "policy_document_id": record.get("policy_document_id"),
                "claim_document_ids": record.get("claim_document_ids"),
                "policy_source_count": result.get("rag_evaluation", {}).get("policy_source_count", 0),
                "claim_source_count": result.get("rag_evaluation", {}).get("claim_source_count", 0),
                "missing_documents": result.get("document_checklist", {}).get("missing_documents", []),
                "rag_warnings": result.get("rag_evaluation", {}).get("warnings", []),
            },
        )
        log_audit_event(
            db,
            actor=current_user["username"],
            role=current_user.get("role", "agent"),
            action="analyze_claim",
            target_type="claim",
            target_id=str(record["id"]),
            details={
                "query": structured_question,
                "policy_category": request.policy_category,
                "policy_document_id": record.get("policy_document_id"),
                "claim_document_ids": record.get("claim_document_ids"),
                "retrieved_sections": result.get("sources", []),
                "result": result.get("decision"),
                "confidence": result.get("confidence"),
                "missing_documents": result.get("document_checklist", {}).get("missing_documents", []),
                "rag_evaluation": result.get("rag_evaluation", {}),
            },
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        record_metric_event(
            db,
            "claim_analysis",
            status="failed",
            duration_ms=(time.perf_counter() - started_at) * 1000,
            details={"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/{upload_type}")
def upload_document(
    upload_type: str,
    category: str = "medical_document",
    replace_existing: bool = False,
    file: UploadFile = File(...),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_permission(current_user, "documents:upload")
    if upload_type not in UPLOAD_TYPES:
        raise HTTPException(status_code=404, detail="Upload endpoint not found")

    original_name = Path(file.filename or "document.pdf").name

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg"}
    if Path(original_name).suffix.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, PNG, JPG, and JPEG files can be processed.",
        )

    if category not in KNOWLEDGE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid knowledge category")

    accessible = get_accessible_categories(current_user.get("role"))
    if accessible is not None and category not in accessible:
        raise HTTPException(status_code=403, detail="You do not have access to this knowledge category")

    file_position = file.file.tell() if hasattr(file.file, "tell") else None
    if file_position is not None:
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(file_position if file_position >= 0 else 0)
    else:
        file_size = 0

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 20 MB.")

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Calculate SHA-256 of the uploaded file to detect duplicates
    import hashlib

    try:
        hasher = hashlib.sha256()
        file.file.seek(0)
        while chunk := file.file.read(1024 * 1024):
            hasher.update(chunk)
        sha256_digest = hasher.hexdigest()
    finally:
        try:
            file.file.seek(0)
        except Exception:
            pass

    existing_record = db.documents.find_one({"sha256": sha256_digest})

    if existing_record and not replace_existing:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "This document has already been indexed.",
                "duplicate": True,
                "existing_document": {
                    "id": existing_record.get("id"),
                    "filename": existing_record.get("filename"),
                    "category": existing_record.get("category"),
                    "status": existing_record.get("status"),
                },
            },
        )

    if existing_record and replace_existing:
        storage.delete(existing_record)
        db.documents.delete_one({"id": existing_record.get("id")})
        db.document_versions.delete_many({"document_id": existing_record.get("id")})

    safe_name = f"{UPLOAD_TYPES[upload_type]}_{uuid4().hex}_{original_name}"
    saved_storage = None

    try:
        # Save file to storage
        saved_storage = storage.save(file.file, safe_name, file.content_type or "application/octet-stream")

        document_id = get_next_id("documents")
        record = {
            "id": document_id,
            "filename": original_name,
            "sha256": sha256_digest,
            "stored_path": saved_storage["stored_path"],
            "storage_backend": saved_storage["storage_backend"],
            "storage_key": saved_storage["storage_key"],
            "content_type": saved_storage.get("content_type") or file.content_type or "",
            "document_type": UPLOAD_TYPES[upload_type],
            "category": category,
            "status": "processing",
            "pages": 0,
            "chunks": 0,
            "word_count": 0,
            "processing_time_seconds": 0,
            "version": 1,
            "uploaded_by": current_user["username"],
            "created_at": datetime.utcnow(),
        }
        db.documents.insert_one(record)
        db.document_versions.insert_one(
            {
                "document_id": document_id,
                "version_number": 1,
                "stored_path": saved_storage["stored_path"],
                "storage_backend": saved_storage["storage_backend"],
                "storage_key": saved_storage["storage_key"],
                "filename": original_name,
                "created_by": current_user["username"],
                "created_at": datetime.utcnow(),
            }
        )

        log_audit_event(
            db,
            actor=current_user["username"],
            role=current_user.get("role", "agent"),
            action="upload_document",
            target_type="document",
            target_id=str(document_id),
            details=f"Queued {original_name} for background indexing into {category}",
        )

        enqueue_indexing_job({
            "document_id": document_id,
            "document_type": UPLOAD_TYPES[upload_type],
            "category": category,
            "content_type": file.content_type or "",
            "uploaded_by": current_user["username"],
            "filename": original_name,
        })

        return {
            "message": "File uploaded and queued for indexing.",
            "filename": original_name,
            "document_type": UPLOAD_TYPES[upload_type],
            "category": category,
            "status": "processing",
            "pages": 0,
            "chunks": 0,
            "word_count": 0,
            "processing_time_seconds": 0,
            "duplicate": False,
            "document_id": record["id"],
        }

    except ValueError as e:
        logging.error("Upload validation error for %s: %s", original_name, e, exc_info=True)
        if saved_storage:
            try:
                storage.delete(saved_storage)
            except Exception:
                logging.exception("Failed to cleanup saved storage after ValueError for %s", original_name)

        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.exception("Unhandled exception during file upload for %s", original_name)
        if saved_storage:
            try:
                storage.delete(saved_storage)
            except Exception:
                logging.exception("Failed to cleanup saved storage after exception for %s", original_name)

        raise HTTPException(status_code=500, detail=str(e))
