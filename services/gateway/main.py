import logging
import os
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

app = FastAPI(title="Insurance API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://3.139.54.15:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_URL = os.getenv("BACKEND_SERVICE_URL", "http://backend:8000")
AUTH_URL = os.getenv("AUTH_SERVICE_URL", BACKEND_URL)
DOCUMENTS_URL = os.getenv("DOCUMENTS_SERVICE_URL", "http://documents:8000")
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://rag:8000")
AI_URL = os.getenv("AI_SERVICE_URL", "http://ai:8000")
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_UPSTREAM_TIMEOUT_SECONDS", "90"))

LOCAL_SERVICE_FALLBACKS = {
    "localhost": "http://127.0.0.1:8000",
    "127.0.0.1": "http://127.0.0.1:8000",
}


def upstream_candidates(base_url: str) -> list[str]:
    candidates = [base_url.rstrip("/")]
    host = urlparse(base_url).hostname
    fallback = LOCAL_SERVICE_FALLBACKS.get(host or "")
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates


async def proxy_json(method: str, base_url: str, path: str, **kwargs):
    timeout_seconds = float(kwargs.pop("timeout_seconds", UPSTREAM_TIMEOUT_SECONDS))
    clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
    upstream_errors: list[str] = []
    async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
        for candidate in upstream_candidates(base_url):
            url = f"{candidate}{path}"
            try:
                logging.debug("Gateway proxy request %s %s", method, url)
                response = await client.request(method, url, **clean_kwargs)
                logging.debug("Gateway upstream response %s %s %s", method, url, response.status_code)
                break
            except httpx.TimeoutException as exc:
                error_message = f"{url}: upstream timed out after {timeout_seconds:g}s"
                logging.error("Gateway upstream timeout: %s (%s)", error_message, type(exc).__name__)
                raise HTTPException(status_code=504, detail=error_message) from exc
            except httpx.RequestError as exc:
                error_message = f"{url}: {exc}"
                logging.error("Gateway upstream request failed: %s", error_message)
                upstream_errors.append(error_message)
        else:
            logging.error("Gateway upstream service unavailable for %s %s: %s", method, path, upstream_errors)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream service unavailable: {', '.join(upstream_errors)}",
            )

        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text}
        if response.is_error:
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            logging.error("Gateway upstream returned error %s %s %s %s", method, url, response.status_code, detail)
            raise HTTPException(status_code=response.status_code, detail=detail)
        return payload


@app.get("/health")
def health():
    return {"status": "healthy", "service": "gateway"}


@app.get("/health/services")
async def service_health():
    services = {
        "auth": (AUTH_URL, "/health"),
        "backend": (BACKEND_URL, "/health"),
        "documents": (DOCUMENTS_URL, "/health"),
        "rag": (RAG_URL, "/health"),
        "ai": (AI_URL, "/health"),
    }
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service, (base_url, path) in services.items():
            checked_urls = []
            for candidate in upstream_candidates(base_url):
                url = f"{candidate}{path}"
                checked_urls.append(url)
                try:
                    response = await client.get(url)
                    results[service] = {
                        "status": "healthy" if response.is_success else "unhealthy",
                        "status_code": response.status_code,
                        "url": url,
                    }
                    break
                except httpx.RequestError:
                    continue
            else:
                results[service] = {
                    "status": "unavailable",
                    "checked_urls": checked_urls,
                }
    overall = "healthy" if all(item["status"] == "healthy" for item in results.values()) else "degraded"
    return {"status": overall, "services": results}


@app.get("/")
def root():
    return {
        "message": "Insurance API Gateway",
        "services": ["auth", "documents", "rag", "ai"],
    }


@app.post("/auth/login")
async def login(payload: dict):
    return await proxy_json("POST", AUTH_URL, "/auth/login", json=payload)


@app.post("/auth/register")
async def register(payload: dict):
    return await proxy_json("POST", AUTH_URL, "/auth/register", json=payload)


@app.post("/auth/verify-email")
async def verify_email(payload: dict):
    return await proxy_json("POST", AUTH_URL, "/auth/verify-email", json=payload)


@app.post("/auth/resend-verification")
async def resend_verification(payload: dict, request: Request):
    headers = {"X-Forwarded-For": request.client.host} if request.client else None
    return await proxy_json("POST", AUTH_URL, "/auth/resend-verification", json=payload, headers=headers)


@app.post("/auth/forgot-password")
async def forgot_password(payload: dict, request: Request):
    headers = {"X-Forwarded-For": request.client.host} if request.client else None
    return await proxy_json("POST", AUTH_URL, "/auth/forgot-password", json=payload, headers=headers)


@app.post("/auth/reset-password")
async def reset_password(payload: dict):
    return await proxy_json("POST", AUTH_URL, "/auth/reset-password", json=payload)


@app.get("/profile")
async def profile(request: Request):
    headers = _get_auth_headers(request)
    if not headers:
        raise HTTPException(status_code=401, detail="Authorization header required")
    return await proxy_json("GET", AUTH_URL, "/profile", headers=headers)


@app.get("/me")
async def me(request: Request):
    headers = _get_auth_headers(request)
    if not headers:
        raise HTTPException(status_code=401, detail="Authorization header required")
    return await proxy_json("GET", BACKEND_URL, "/me", headers=headers)


def _get_auth_headers(request: Request | None):
    if request is None:
        return None
    auth_header = request.headers.get("authorization")
    return {"Authorization": auth_header} if auth_header else None


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), category: str = Form("policy"), request: Request = None):
    contents = await file.read()
    headers = _get_auth_headers(request)
    return await proxy_json(
        "POST",
        BACKEND_URL,
        "/documents/upload",
        files={"file": (file.filename, contents, file.content_type or "application/pdf")},
        data={"category": category},
        headers=headers,
    )


@app.get("/documents")
async def documents(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/documents", headers=headers)


@app.get("/document/{document_id}/download")
async def document_download(document_id: int, request: Request):
    headers = _get_auth_headers(request)
    client = httpx.AsyncClient(timeout=30.0)
    upstream_errors: list[str] = []
    for candidate in upstream_candidates(BACKEND_URL):
        url = f"{candidate}/document/{document_id}/download"
        try:
            response = await client.get(url, headers=headers, follow_redirects=True)
            break
        except httpx.RequestError as exc:
            upstream_errors.append(str(exc.request.url))
    else:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service unavailable: {', '.join(upstream_errors)}",
        )

    if response.is_error:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        await response.aclose()
        await client.aclose()
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise HTTPException(status_code=response.status_code, detail=detail)

    streaming_headers = {}
    if "content-disposition" in response.headers:
        streaming_headers["content-disposition"] = response.headers["content-disposition"]

    async def close_upstream():
        await response.aclose()
        await client.aclose()

    return StreamingResponse(
        response.aiter_bytes(),
        media_type=response.headers.get("content-type", "application/octet-stream"),
        headers=streaming_headers,
        background=BackgroundTask(close_upstream),
    )


@app.delete("/document/{document_id}")
async def document_delete(document_id: int, request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("DELETE", BACKEND_URL, f"/document/{document_id}", headers=headers)


@app.post("/document/{document_id}/reindex")
async def document_reindex(document_id: int, request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("POST", BACKEND_URL, f"/document/{document_id}/reindex", headers=headers)


@app.get("/policies")
async def policies(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/policies", headers=headers)


@app.get("/upload-history")
async def upload_history(request: Request, document_type: str | None = None):
    headers = _get_auth_headers(request)
    params = {"document_type": document_type} if document_type else None
    return await proxy_json("GET", BACKEND_URL, "/upload-history", headers=headers, params=params)


@app.get("/knowledge-categories")
async def knowledge_categories(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/knowledge-categories", headers=headers)


@app.post("/rag/search")
async def rag_search(payload: dict):
    return await proxy_json("POST", RAG_URL, "/rag/search", json=payload)


@app.post("/rag/index")
async def rag_index(payload: dict):
    return await proxy_json("POST", RAG_URL, "/rag/index", json=payload)


@app.post("/chat")
async def chat(payload: dict, request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json(
        "POST",
        BACKEND_URL,
        "/chat",
        json=payload,
        headers=headers,
        timeout_seconds=float(os.getenv("CHAT_UPSTREAM_TIMEOUT_SECONDS", "90")),
    )


@app.post("/claim/analyze")
async def claim_analyze(payload: dict, request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json(
        "POST",
        BACKEND_URL,
        "/claim/analyze",
        json=payload,
        headers=headers,
        timeout_seconds=float(os.getenv("CLAIM_UPSTREAM_TIMEOUT_SECONDS", "90")),
    )


@app.get("/claims")
async def claims(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/claims", headers=headers)


@app.get("/claim/{claim_id}")
async def claim_detail(claim_id: int, request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, f"/claim/{claim_id}", headers=headers)


@app.post("/{upload_type}")
async def upload_document(
    upload_type: str,
    file: UploadFile = File(...),
    category: str = Query("policy"),
    replace_existing: bool = Query(False),
    request: Request = None,
):
    headers = _get_auth_headers(request)
    response = await proxy_json(
        "POST",
        BACKEND_URL,
        f"/{upload_type}",
        params={"category": category, "replace_existing": replace_existing},
        files={"file": (file.filename, await file.read(), file.content_type or "application/octet-stream")},
        headers=headers,
    )
    return response


@app.get("/dashboard")
async def dashboard(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/dashboard", headers=headers)


@app.get("/analytics")
async def analytics(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/analytics", headers=headers)


@app.get("/notifications")
async def notifications(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/notifications", headers=headers)


@app.get("/admin/overview")
async def admin_overview(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/admin/overview", headers=headers)


@app.get("/settings")
async def settings(request: Request):
    headers = _get_auth_headers(request)
    return await proxy_json("GET", BACKEND_URL, "/settings", headers=headers)
