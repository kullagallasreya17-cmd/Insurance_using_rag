# Enterprise Insurance RAG Application

React + FastAPI application for insurance document ingestion, grounded RAG chat, claim analysis, analytics, notifications, and admin operations.

## Features

- Landing page, login, and registration
- JWT authenticated portal
- Dashboard, documents, policies, uploads, AI chat, claim analysis, claims, analytics, notifications, profile, settings, and admin pages
- PDF/image upload with text extraction, chunking, Gemini embeddings, and MongoDB Atlas vector search storage
- Grounded chatbot that answers from retrieved insurance document chunks
- Claim analysis with stored audit records
- FastAPI Swagger documentation at `http://127.0.0.1:8000/docs`

## Run Backend

Use the normal startup command below on Windows. Avoid `--reload` in PowerShell because the Uvicorn file watcher can hit a Windows socket/watch error and keep reloading unnecessarily.

```powershell
cd D:\projects\Insurance_using_RAG\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

If you want live reload while coding, prefer a Linux shell or run the backend through Docker instead of enabling the Windows file watcher.

## Run Frontend

```powershell
cd D:\projects\Insurance_using_RAG\frontend
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

Default admin:

```text
username: admin
password: admin123
```

## Enterprise Architecture

See [ENTERPRISE_ARCHITECTURE.md](ENTERPRISE_ARCHITECTURE.md) for the microservices target design, communication patterns, endpoint summary, environment variables, diagrams, and deployment notes.

## Scalable Docker Run

Create a local `.env` from `.env.example`, set `MONGO_URI` for MongoDB Atlas, and use local document storage:

```text
STORAGE_BACKEND=local
```

Then run:

```powershell
docker compose up --build --scale backend=3
```

## Insurance AI Web Search Agent

Chat requests are routed deterministically:

- `POLICY_ONLY` uses the existing MongoDB Atlas policy RAG.
- `WEB_ONLY` uses the configured Tavily search tool for current hospitals, treatments, and approximate costs.
- `POLICY_AND_WEB` retrieves policy evidence and web evidence separately, then sends both labeled contexts to Gemini.

Copy `.env.example` to `backend/.env` and configure `WEB_SEARCH_API_KEY`. The web tool is optional: when the key is missing, policy-only questions continue to use the existing RAG and web requests fail with a user-safe empty result. Web pages are treated as untrusted reference data and cannot override an explicit policy clause.

The authenticated `POST /api/search` endpoint accepts:

```json
{"query": "What is the approximate cost of knee replacement surgery in Bangalore?", "max_results": 5}
```

Run the web-agent tests with:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_web_search_agent.py -q
```

The Docker setup runs API replicas with MongoDB-backed durable indexing jobs, MongoDB-backed cache/presence state, and MongoDB Atlas Vector Search.
