import os

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AI Service")

BACKEND_URL = os.getenv("BACKEND_SERVICE_URL", "http://backend:8000").rstrip("/")


class ChatRequest(BaseModel):
    question: str


class ClaimRequest(BaseModel):
    question: str
    claim_amount: float | None = None
    policy_category: str | None = None


async def proxy_json(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(timeout=60.0) as client:
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
    return {"status": "healthy", "service": "ai", "mode": "backend-adapter"}


@app.post("/chat")
async def chat(request: ChatRequest, authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("POST", "/chat", json=request.model_dump(), headers=headers)


@app.post("/claim/analyze")
async def analyze_claim(request: ClaimRequest, authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("POST", "/claim/analyze", json=request.model_dump(), headers=headers)
