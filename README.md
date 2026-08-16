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

Create a local `.env` from `.env.example`, set `MONGO_URI` for MongoDB Atlas, and use S3-compatible object storage in production:

```text
STORAGE_BACKEND=s3
S3_BUCKET=your-bucket-name
S3_PREFIX=insurance-documents
```

Then run:

```powershell
docker compose up --build --scale backend=3
```

The Docker setup runs API replicas with MongoDB-backed durable indexing jobs, MongoDB-backed cache/presence state, and MongoDB Atlas Vector Search. For multi-node/cloud deployments, use `STORAGE_BACKEND=s3` so every replica can read uploaded documents from shared object storage.
