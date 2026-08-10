# Microservices Project Structure

This project is now organized as a microservices-style solution while preserving the current functional pages and components from the existing insurance application.

## Root Structure

```text
Insurance_using_RAG/
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   └── ...
├── services/
│   ├── gateway/
│   │   ├── main.py
│   │   └── Dockerfile
│   ├── auth/
│   │   ├── main.py
│   │   └── Dockerfile
│   ├── documents/
│   │   ├── main.py
│   │   └── Dockerfile
│   ├── rag/
│   │   ├── main.py
│   │   └── Dockerfile
│   └── ai/
│       ├── main.py
│       └── Dockerfile
├── docker-compose.microservices.yml
├── README.md
├── ENTERPRISE_ARCHITECTURE.md
└── ...
```

## Service Responsibilities

### API Gateway
- Entry point for all frontend requests.
- Routes requests to auth, documents, rag, and AI services.

### Auth Service
- Login
- Registration
- Profile
- Role-based access

### Document Service
- PDF/image upload
- Policy and document metadata
- Document listing

### RAG Service
- Text extraction
- Chunking
- Embedding generation
- Semantic search
- Vector retrieval

### AI Service
- Chat responses
- Claim analysis
- Decision generation and confidence detection

## Frontend Pages Preserved

The frontend still contains the same pages and components already designed:

- Landing
- Login
- Register
- Dashboard
- Documents
- Policies
- UploadPolicy
- UploadReports
- ClaimAnalysis
- Claims
- KnowledgeBase
- Chatbot
- Analytics
- Notifications
- Profile
- Settings
- AdminDashboard

## Next Step

The next real implementation step is to move the current FastAPI logic from the monolithic backend into these separate services, while keeping the existing frontend working through the gateway.
