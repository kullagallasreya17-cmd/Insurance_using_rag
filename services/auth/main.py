import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Auth Service")

BACKEND_URL = os.getenv("BACKEND_SERVICE_URL", "http://backend:8000").rstrip("/")


async def proxy_json(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, f"{BACKEND_URL}{path}", **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}
    if response.is_error:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise HTTPException(status_code=response.status_code, detail=detail)
    return payload


@app.get("/health")
def health():
    return {"status": "healthy", "service": "auth", "mode": "backend-adapter"}


@app.post("/auth/register")
async def register(payload: dict):
    return await proxy_json("POST", "/auth/register", json=payload)


@app.post("/auth/forgot-password")
async def forgot_password(payload: dict, request: Request):
    return await proxy_json("POST", "/auth/forgot-password", json=payload, headers={"X-Forwarded-For": request.client.host if request.client else ""})


@app.post("/auth/reset-password")
async def reset_password(payload: dict):
    return await proxy_json("POST", "/auth/reset-password", json=payload)


@app.post("/auth/verify-email")
async def verify_email(payload: dict):
    return await proxy_json("POST", "/auth/verify-email", json=payload)


@app.post("/auth/resend-verification")
async def resend_verification(payload: dict, request: Request):
    return await proxy_json("POST", "/auth/resend-verification", json=payload, headers={"X-Forwarded-For": request.client.host if request.client else ""})


@app.post("/auth/login")
async def login(payload: dict):
    return await proxy_json("POST", "/auth/login", json=payload)


@app.get("/profile")
async def profile(authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("GET", "/profile", headers=headers)


@app.get("/users")
async def list_users(authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("GET", "/admin/overview", headers=headers)
