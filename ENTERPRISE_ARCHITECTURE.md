# Enterprise Insurance RAG Architecture

## Current Implementation

This repository runs as a React + FastAPI insurance RAG application. The backend is currently deployed as one modular FastAPI service, with API boundaries that map to future microservices:

- Authentication Service: `/auth/register`, `/auth/login`, `/auth/logout`
- User Service: `/me`, `/profile`
- Document Service: `/upload-policy`, `/upload-report`, `/documents`, `/document/{id}`, `/policies`
- RAG Service: document loading, chunking, embeddings, MongoDB Atlas vector search storage, `/debug/retrieve`
- Chat Service: `/chat`
- Claim Service: `/claim/analyze`, `/claims`, `/claim/{id}`
- Notification Service: `/notifications`
- API Gateway: current FastAPI app; production target is a separate gateway service

## Target Microservices

Each production service should have its own codebase, Dockerfile, `.env`, configuration, API layer, tests, and deployment pipeline.

| Service | Responsibility | Database | Communication |
| --- | --- | --- | --- |
| API Gateway | Auth verification, routing, rate limits, CORS | Redis for cache/rate limits | REST to services |
| Authentication Service | Register, login, JWT, password hashing | PostgreSQL | REST |
| User Service | Profiles, roles, permissions | PostgreSQL | REST |
| Document Service | Uploads, metadata, validation, lifecycle | PostgreSQL + object storage | REST + RabbitMQ |
| RAG Service | Extraction, chunking, embeddings, retrieval | MongoDB Atlas Vector Search or PGVector | REST + RabbitMQ |
| Chat Service | Chat requests, grounded answers, history | MongoDB for chat history | REST |
| Claim Service | Claim decisioning and audit records | PostgreSQL | REST + RabbitMQ |
| Notification Service | Email, in-app alerts, processing events | MongoDB or PostgreSQL | RabbitMQ |

## Communication

Synchronous REST:

- Login and registration
- Fetch dashboard data
- Fetch profile
- Fetch policies/documents/claims
- Chat request and response
- Claim detail lookup

Asynchronous RabbitMQ or Kafka:

- PDF processing after upload
- OCR and embedding generation
- Claim processing workflow
- Notification delivery
- Audit logging

Reasoning: user-facing reads and short commands need immediate REST responses. Long-running or failure-prone tasks like OCR, embeddings, notifications, and audit logging should be event-driven so the UI remains responsive and services can retry independently.

## RAG Flow

```text
User
  |
  v
React Frontend
  |
  v
API Gateway / FastAPI
  |
  v
Document Service uploads PDF
  |
  v
RAG Service extracts text
  |
  v
Text splitter creates chunks
  |
  v
Embedding model creates vectors
  |
  v
MongoDB Atlas Vector Search stores vectors
  |
  v
Chat question creates query embedding
  |
  v
Retriever fetches top-k chunks
  |
  v
LLM receives question + retrieved context
  |
  v
Grounded answer returned to user
```

The LLM must not answer insurance questions without retrieved context.

## Database Choices

- PostgreSQL: transactional records such as users, roles, document metadata, claim audits.
- MongoDB Atlas Vector Search or PGVector: semantic vector search over policy and evidence chunks.
- MongoDB: flexible chat history and notification payloads.
- Redis: rate limiting, short-lived cache, gateway sessions, queue locks.
- Elasticsearch: optional centralized logs and search over operational events.

## API Summary

Authentication:

- `POST /auth/register`
  - Request: `{ "username": "agent1", "password": "secret", "full_name": "Agent One", "role": "agent" }`
  - Response: `{ "access_token": "...", "token_type": "bearer", "user": {...} }`
- `POST /auth/login`
  - Request: `{ "username": "admin", "password": "admin123" }`
  - Response: `{ "access_token": "...", "token_type": "bearer", "user": {...} }`
- `POST /auth/logout`
  - Response: `{ "message": "admin logged out successfully" }`

Documents:

- `POST /upload-policy?category=life_policy`
  - Form data: `file`
  - Response: `{ "message": "...", "filename": "...", "pages": 3, "chunks": 4 }`
- `GET /documents`
  - Response: `{ "documents": [...] }`
- `DELETE /document/{id}`
  - Response: `{ "message": "Document metadata deleted", "id": 1 }`
- `GET /policies`
  - Response: `{ "policies": [...] }`

RAG and Chat:

- `POST /chat`
  - Request: `{ "question": "What is the sum assured?" }`
  - Response: `{ "question": "...", "answer": "..." }`
- `POST /debug/retrieve`
  - Request: `{ "question": "What are the exclusions?" }`
  - Response: `{ "chunks": [...] }`

Claims:

- `POST /claim/analyze`
  - Request: `{ "question": "...", "claim_amount": 25000, "policy_category": "life_policy" }`
  - Response: `{ "decision": "needs_review", "confidence": "medium", "rationale": "...", "sources": [...] }`
- `GET /claims`
  - Response: `{ "claims": [...] }`
- `GET /claim/{id}`
  - Response: claim detail object

Dashboard and Operations:

- `GET /dashboard`
- `GET /analytics`
- `GET /notifications`
- `GET /profile`
- `GET /settings`
- `GET /admin/overview`

## Environment Variables

Authentication Service:

```text
DATABASE_URL=
JWT_SECRET=
JWT_EXPIRE=
```

RAG Service:

```text
GOOGLE_API_KEY=
GOOGLE_EMBEDDING_MODEL=models/gemini-embedding-001
MONGO_URI=
MONGO_DB=insurance
MONGO_COLLECTION=document_vectors
```

Document Service:

```text
UPLOAD_PATH=./documents
MAX_FILE_SIZE_MB=20
ALLOWED_FILE_TYPES=pdf,png,jpg,jpeg
```

Gateway:

```text
FRONTEND_ORIGIN=http://localhost:5173
RATE_LIMIT_PER_MINUTE=120
REDIS_URL=
```

## Security

Implemented or prepared:

- JWT authentication
- Role-based admin endpoint
- PBKDF2-SHA256 password hashing
- CORS middleware
- File extension validation
- SQLAlchemy ORM protection against SQL injection
- Pydantic request validation
- Swagger docs through FastAPI at `/docs`

Production additions:

- HTTPS at gateway/load balancer
- Strict CORS origin allowlist
- Rate limiting through API Gateway + Redis
- Malware scanning for uploaded files
- Object storage with signed URLs
- Central audit logs
- Secret manager instead of raw `.env` files

## Sequence Diagram

```text
Frontend -> API Gateway: POST /upload-policy
API Gateway -> Auth Service: validate JWT
API Gateway -> Document Service: store file + metadata
Document Service -> Queue: document.uploaded
Queue -> RAG Service: process document
RAG Service -> RAG Service: extract, chunk, embed
RAG Service -> Vector DB: store chunks
RAG Service -> Notification Service: document.indexed
Notification Service -> Frontend: notification appears

Frontend -> Chat Service: POST /chat
Chat Service -> RAG Service: retrieve top-k chunks
RAG Service -> Vector DB: similarity search
RAG Service -> Chat Service: relevant chunks
Chat Service -> LLM: question + context
LLM -> Chat Service: grounded answer
Chat Service -> Frontend: answer
```

## ER Diagram

```text
User
  id PK
  username
  full_name
  role
  hashed_password
  created_at

DocumentRecord
  id PK
  filename
  stored_path
  document_type
  category
  status
  pages
  chunks
  uploaded_by -> User.username
  created_at

ClaimAnalysisRecord
  id PK
  question
  decision
  confidence
  rationale
  missing_information
  created_by -> User.username
  created_at
```

## Deployment Guide

Local backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Local frontend:

```powershell
cd frontend
npm.cmd run dev
```

Docker:

```powershell
docker compose up --build
```

For full microservices deployment, split the current FastAPI modules into service repositories following the boundaries above, then route all browser traffic through the API Gateway.
