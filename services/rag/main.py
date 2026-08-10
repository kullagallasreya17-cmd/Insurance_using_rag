import os

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="RAG Service")

BACKEND_URL = os.getenv("BACKEND_SERVICE_URL", "http://backend:8000").rstrip("/")


class QueryRequest(BaseModel):
    question: str


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
    return {"status": "healthy", "service": "rag", "mode": "backend-adapter"}


@app.post("/rag/search")
async def search_rag(payload: QueryRequest, authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("POST", "/debug/retrieve", json=payload.model_dump(), headers=headers)


@app.post("/rag/index")
async def index_documents(payload: dict, authorization: str = Header(default="")):
    document_id = payload.get("document_id")
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("POST", f"/document/{document_id}/reindex", headers=headers)
