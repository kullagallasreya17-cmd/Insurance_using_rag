import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from database import get_db
from database import verify_password as db_verify_password
from pathlib import Path


load_dotenv(Path(__file__).resolve().parent / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
ACTIVE_USER_TTL_SECONDS = 300

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(data: dict):
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def mark_user_active(user, db):
    db.active_users.update_one(
        {"username": user["username"]},
        {
            "$set": {
                "username": user["username"],
                "role": user.get("role", "agent"),
                "last_seen": datetime.utcnow(),
            }
        },
        upsert=True,
    )


def clear_active_user(username, db):
    db.active_users.delete_one({"username": username})


def get_active_users(db):
    cutoff = datetime.utcnow() - timedelta(seconds=ACTIVE_USER_TTL_SECONDS)
    db.active_users.delete_many({"last_seen": {"$lt": cutoff}})
    users = db.active_users.find({}, {"_id": 0}).sort("last_seen", -1)
    return [
        {
            **user,
            "last_seen": user["last_seen"].timestamp() if hasattr(user.get("last_seen"), "timestamp") else user.get("last_seen"),
        }
        for user in users
    ]


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.users.find_one({"username": username})
    if user is None:
        raise credentials_exception

    mark_user_active(user, db)
    return user
