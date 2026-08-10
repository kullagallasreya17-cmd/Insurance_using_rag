import os

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

app = FastAPI(title="Document Service")

BACKEND_URL = os.getenv("BACKEND_SERVICE_URL", "http://backend:8000").rstrip("/")


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
    return {"status": "healthy", "service": "documents", "mode": "backend-adapter"}


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("medical_document"),
    authorization: str = Header(default=""),
):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json(
        "POST",
        "/upload-policy",
        params={"category": category},
        files={"file": (file.filename, await file.read(), file.content_type or "application/octet-stream")},
        headers=headers,
    )


@app.get("/documents")
async def list_documents(authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("GET", "/documents", headers=headers)


@app.get("/policies")
async def list_policies(authorization: str = Header(default="")):
    headers = {"Authorization": authorization} if authorization else None
    return await proxy_json("GET", "/policies", headers=headers)
