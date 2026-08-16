import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import mimetypes

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse

from auth import clear_active_user, create_access_token, get_current_user
from agents.insurance_agent import InsuranceAgent
from claim_engine import analyze_claim
from database import get_database, get_db, init_db, get_next_id, hash_password, verify_password
from rag.background_indexer import BackgroundIndexer
from rag.mongo_indexer import MongoJobIndexer
from rag.rq_indexer import RQJobIndexer
from rag.indexer import extract_document_preview, index_document
from rag.retriever import retrieve_documents
from schemas import ChatRequest, ClaimRequest, LoginRequest, RegisterRequest
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
KNOWLEDGE_CATEGORIES = [
    "health_policy",
    "vehicle_policy",
    "life_policy",
    "claim_procedure",
    "terms_conditions",
    "faq",
    "medical_document",
    "other",
]

ROLE_CATEGORY_ACCESS = {
    "admin": None,
    "analyst": {"health_policy", "vehicle_policy", "life_policy", "claim_procedure", "other"},
    "agent": {"health_policy", "other"},
    "auditor": {"health_policy", "vehicle_policy", "life_policy", "claim_procedure", "terms_conditions", "faq", "other"},
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
        "settings:edit",
    ],
    "analyst": [
        "documents:read",
        "chat:ask",
        "claims:analyze",
        "claims:read",
        "dashboard:read",
        "analytics:read",
    ],
    "agent": [
        "documents:upload",
        "documents:read",
        "chat:ask",
        "claims:analyze",
        "dashboard:read",
    ],
    "auditor": [
        "documents:read",
        "chat:ask",
        "claims:read",
        "dashboard:read",
        "analytics:read",
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
        return

    db = next(get_db())
    document = db.documents.find_one({"id": document_id})
    if not document:
        return

    try:
        # mark document as processing
        db.documents.update_one({"id": document_id}, {"$set": {"status": "processing", "started_indexing_at": datetime.utcnow()}})
        with storage.open_for_read(document) as file_path:
            if not file_path.exists():
                raise FileNotFoundError("Stored document file not found")

            index_result = index_document(
                file_path,
                job.get("document_type", document.get("document_type", "unknown")),
                job.get("category", document.get("category", "unknown")),
                job.get("content_type", document.get("content_type", "application/octet-stream")),
            )
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logging.error("Indexing failed for document %s: %s", document_id, error_message)
        db.documents.update_one({"id": document_id}, {"$set": {"status": "failed", "indexing_error": str(exc), "indexing_error_trace": traceback.format_exc()}})
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

    db.documents.update_one(
        {"id": document_id},
        {
            "$set": {
                "status": "indexed",
                "pages": index_result.get("pages", 0),
                "chunks": index_result.get("chunks", 0),
                "word_count": index_result.get("word_count", 0),
                "processing_time_seconds": index_result.get("processing_time_seconds", 0),
            }
        },
    )

    log_audit_event(
        db,
        actor=job.get("uploaded_by", "system"),
        role="system",
        action="index_document_completed",
        target_type="document",
        target_id=str(document_id),
        details=f"Indexed {job.get('filename', document.get('filename', 'unknown'))} into {document.get('category', 'unknown')}",
    )


if INDEXING_BACKEND == "mongo":
    background_indexer = MongoJobIndexer(
        db_provider=get_database,
        handler=process_indexing_job,
        worker_count=LOCAL_INDEXER_WORKERS,
        lease_seconds=INDEXER_LEASE_SECONDS,
    )
elif INDEXING_BACKEND == "rq":
    background_indexer = RQJobIndexer(redis_url=REDIS_URL)
else:
    background_indexer = BackgroundIndexer(handler=process_indexing_job, worker_count=LOCAL_INDEXER_WORKERS)


def enqueue_indexing_job(payload: dict) -> str:
    return background_indexer.enqueue(payload)


def get_accessible_categories(role: str | None):
    if not role:
        return {"health_policy"}
    categories = ROLE_CATEGORY_ACCESS.get((role or "").lower())
    return categories


def get_role_permissions(role: str | None) -> list[str]:
    return ROLE_PERMISSIONS.get((role or "").lower(), ["documents:read", "chat:ask"])


def format_datetime(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def resolve_document_file(document: dict, db):
    with storage.open_for_read(document) as stored_path:
        if stored_path.exists():
            return stored_path
    return None


def log_audit_event(db, actor: str, role: str, action: str, target_type: str = "", target_id: str = "", details: str = ""):
    db.audit_logs.insert_one(
        {
            "actor": actor,
            "actor_role": role,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "created_at": datetime.utcnow(),
        }
    )

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


@app.post("/auth/login")
def login(request: LoginRequest, db = Depends(get_db)):
    user = db.users.find_one({"username": request.username})
    if not user or not verify_password(request.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user["username"], "role": user.get("role", "agent")})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "role": user.get("role", "agent"),
        },
    }


@app.post("/auth/register")
def register(request: RegisterRequest, db = Depends(get_db)):
    existing_user = db.users.find_one({"username": request.username})
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    user_id = get_next_id("users")
    user = {
        "id": user_id,
        "username": request.username,
        "full_name": request.full_name,
        "role": "agent",
        "hashed_password": hash_password(request.password),
        "created_at": datetime.utcnow(),
    }
    db.users.insert_one(user)

    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
    }


@app.post("/auth/logout")
def logout(db = Depends(get_db), current_user = Depends(get_current_user)):
    clear_active_user(current_user["username"], db)
    return {"message": f"{current_user['username']} logged out successfully"}


@app.get("/me")
def me(current_user = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "full_name": current_user.get("full_name"),
        "role": current_user.get("role", "agent"),
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
        "created_at": format_datetime(document.get("created_at")),
    }


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
            "role": current_user.get("role", "agent"),
            "created_at": format_datetime(current_user.get("created_at")),
        },
        "activity": {
            "documents_uploaded": documents_uploaded,
            "claims_created": claims_created,
        },
        "permissions": [
            "documents:upload",
            "documents:read",
            "chat:ask",
            "claims:analyze",
            "dashboard:read",
        ],
    }


@app.get("/knowledge-categories")
def knowledge_categories(current_user = Depends(get_current_user)):
    accessible = get_accessible_categories(current_user.get("role", "agent"))
    if accessible is None:
        return {"categories": KNOWLEDGE_CATEGORIES}
    return {"categories": [category for category in KNOWLEDGE_CATEGORIES if category in accessible]}


@app.get("/documents")
def list_documents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    accessible = get_accessible_categories(current_user.get("role", "agent"))
    query = {}
    if accessible is not None:
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
    document = db.documents.find_one({"id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

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
    policy_docs = list(db.documents.find({"document_type": "policy"}).sort("created_at", -1).limit(200))
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
                "created_at": format_datetime(doc.get("created_at")),
            }
            for doc in policy_docs
        ]
    }


@app.get("/dashboard")
def dashboard(
    db = Depends(get_db),
    request: Request = None,
):
    # Try to resolve a JWT from the Authorization header; allow anonymous access for the dashboard
    current_user = None
    auth_header = None
    try:
        auth_header = request.headers.get("authorization") if request is not None else None
    except Exception:
        auth_header = None

    if auth_header and isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            current_user = get_current_user(token=token, db=db)
        except HTTPException:
            current_user = None

    total_documents = db.documents.count_documents({})
    policies = db.documents.count_documents({"document_type": "policy"})
    reports = db.documents.count_documents({"document_type": {"$ne": "policy"}})
    claims = db.claim_analyses.count_documents({})

    claim_rows = list(
        db.claim_analyses.find(
            {},
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
            {},
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
            {},
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
        {"$group": {"_id": None, "total_chunks": {"$sum": {"$ifNull": ["$chunks", 0]}}}},
    ]))
    total_chunks = int(total_chunks_agg[0]["total_chunks"] or 0) if total_chunks_agg else 0

    avg_indexing_time_agg = list(db.documents.aggregate([
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
        "recent_documents": recent_documents,
        "recent_claims": recent_claims,
    }


@app.get("/analytics")
def analytics(
    db = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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
            if isinstance(details, str) and details.startswith("Asked:"):
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
    recent_documents = list(db.documents.find().sort("created_at", -1).limit(5))
    recent_claims = list(db.claim_analyses.find().sort("created_at", -1).limit(5))
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
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    users = list(db.users.find({}, {"_id": 0}).sort("created_at", -1).limit(50))
    audit_logs = list(db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(10))
    return {
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
                "details": log.get("details"),
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


@app.get("/claims")
def list_claims(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    total = db.claim_analyses.count_documents({})
    claims = list(db.claim_analyses.find().sort("created_at", -1).skip(offset).limit(limit))
    return {
        "claims": [
            {
                "id": claim.get("id"),
                "question": claim.get("question"),
                "decision": claim.get("decision"),
                "confidence": claim.get("confidence"),
                "rationale": claim.get("rationale"),
                "missing_information": claim.get("missing_information"),
                "explanation_trail": claim.get("explanation_trail"),
                "evidence_summary": claim.get("evidence_summary"),
                "created_by": claim.get("created_by"),
                "created_at": format_datetime(claim.get("created_at")),
            }
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
    claim = db.claim_analyses.find_one({"id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    return {
        "id": claim.get("id"),
        "question": claim.get("question"),
        "decision": claim.get("decision"),
        "confidence": claim.get("confidence"),
        "rationale": claim.get("rationale"),
        "missing_information": claim.get("missing_information"),
        "explanation_trail": claim.get("explanation_trail"),
        "evidence_summary": claim.get("evidence_summary"),
        "sources": claim.get("sources", []),
        "created_by": claim.get("created_by"),
        "created_at": format_datetime(claim.get("created_at")),
    }


@app.post("/chat")
def chat(request: ChatRequest, db = Depends(get_db), current_user = Depends(get_current_user)):

    try:

        result = agent.ask_with_metrics(request.question)
        log_audit_event(
            db,
            actor=current_user["username"],
            role=current_user.get("role", "agent"),
            action="ask_chat",
            target_type="chat",
            target_id="",
            details=f"Asked: {request.question[:120]}",
        )

        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "confidence": result.get("confidence", "medium"),
            "retrieval_ms": result.get("retrieval_ms", 0),
            "generation_ms": result.get("generation_ms", 0),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/debug/retrieve")
def debug_retrieve(request: ChatRequest, current_user = Depends(get_current_user)):
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
        )
    db.documents.update_one(
        {"id": document_id},
        {
            "$set": {
                "status": "indexed",
                "pages": index_result.get("pages", 0),
                "chunks": index_result.get("chunks", 0),
                "word_count": index_result.get("word_count", 0),
                "processing_time_seconds": index_result.get("processing_time_seconds", 0),
            }
        },
    )

    return {
        "message": "Document re-indexed successfully.",
        "pages": index_result["pages"],
        "chunks": index_result["chunks"],
        "word_count": index_result.get("word_count", 0),
        "processing_time_seconds": index_result.get("processing_time_seconds", 0),
    }


@app.post("/claim/analyze")
def claim_analyze(
    request: ClaimRequest,
    db = Depends(get_db),
    current_user = Depends(get_current_user),
):
    try:
        structured_question = request.question or request.treatment_details or request.diagnosis or "claim coverage assessment"
        if request.treatment_details:
            structured_question = f"{request.treatment_details}. Diagnosis: {request.diagnosis or 'not provided'}. Hospital: {request.hospital_name or 'not provided'}. Admission date: {request.admission_date or 'not provided'}."

        result = analyze_claim(
            question=structured_question,
            claim_amount=request.claim_amount or request.bill_amount,
            policy_category=request.policy_category,
        )

        evidence_summary = "; ".join(result.get("covered_items", []) + result.get("exclusions", [])) or "No structured evidence extracted"
        record = {
            "id": get_next_id("claim_analyses"),
            "question": structured_question,
            "decision": result["decision"],
            "confidence": result["confidence"],
            "rationale": result["rationale"],
            "missing_information": ", ".join(result.get("missing_information", [])),
            "explanation_trail": result.get("next_steps", []),
            "evidence_summary": evidence_summary,
            "sources": result.get("sources", []),
            "created_by": current_user["username"],
            "created_at": datetime.utcnow(),
        }
        db.claim_analyses.insert_one(record)
        log_audit_event(
            db,
            actor=current_user["username"],
            role=current_user.get("role", "agent"),
            action="analyze_claim",
            target_type="claim",
            target_id=str(record["id"]),
            details=f"Claim decision {result['decision']} with {result['confidence']} confidence",
        )

        return result
    except Exception as e:
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
