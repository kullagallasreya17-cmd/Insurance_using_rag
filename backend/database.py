import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, ReturnDocument


dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "insurance")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI must be set in the environment or .env file")

client: MongoClient | None = None
db = None


def get_mongo_client() -> MongoClient:
    global client
    if client is None:
        client = MongoClient(MONGO_URI)
    return client


def get_database():
    global db
    if db is None:
        db = get_mongo_client()[MONGO_DB]
    return db


def get_db():
    yield get_database()


PASSWORD_ITERATIONS = 260000


def hash_password(password: str) -> str:
    import hashlib
    import os

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    import hashlib
    import hmac

    try:
        algorithm, iterations, salt_hex, digest_hex = hashed_password.split("$")
        if algorithm != "pbkdf2_sha256":
            return False

        expected_digest = bytes.fromhex(digest_hex)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual_digest, expected_digest)
    except ValueError:
        return False


def get_next_id(collection_name: str) -> int:
    database = get_database()
    result = database.counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(result["seq"])


def init_db():
    database = get_database()
    database.users.update_many({"is_active": {"$exists": False}}, {"$set": {"is_active": True}})
    database.users.update_many({"email_verified": {"$exists": False}}, {"$set": {"email_verified": False}})
    database.users.update_many({"token_version": {"$exists": False}}, {"$set": {"token_version": 0}})
    database.users.create_index("username", unique=True)
    database.users.create_index("email", unique=True, sparse=True)
    database.email_verification_tokens.create_index("token_hash", unique=True)
    database.email_verification_tokens.create_index("expires_at", expireAfterSeconds=0)
    database.password_reset_tokens.create_index("token_hash", unique=True)
    database.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    database.documents.create_index("id", unique=True)
    database.documents.create_index("filename")
    database.documents.create_index("category")
    database.documents.create_index("uploaded_by")
    database.documents.create_index("created_at")
    database.document_versions.create_index([("document_id", ASCENDING), ("version_number", ASCENDING)])
    database.claim_analyses.create_index("id", unique=True)
    database.claim_analyses.create_index("created_at")
    database.claim_analyses.create_index("created_by")
    database.audit_logs.create_index("created_at")
    database.audit_logs.create_index("action")
    database.monitoring_events.create_index("created_at")
    database.monitoring_events.create_index("event_type")
    database.monitoring_events.create_index("status")
    database.active_users.create_index("last_seen")
    database.rag_cache.create_index("expires_at", expireAfterSeconds=0)
    database.indexing_jobs.create_index("created_at")

    if database.users.count_documents({"username": "admin"}) == 0:
        database.users.insert_one(
            {
                "id": get_next_id("users"),
                "username": "admin",
                "full_name": "Admin User",
                "role": "admin",
                "hashed_password": hash_password("admin123"),
                "password_hash": hash_password("admin123"),
                "email": os.getenv("ADMIN_EMAIL", ""),
                "is_active": True,
                "email_verified": False,
                "token_version": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )
