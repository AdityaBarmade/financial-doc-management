# 📊 FastAPI Financial Document Management System

> A production-ready backend for managing financial documents with **AI-powered semantic search** using RAG (Retrieval-Augmented Generation).

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue) ![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-orange)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  /auth   │ │  /docs   │ │  /users  │ │    /rag       │  │
│  │  /roles  │ │          │ │          │ │    search     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │
│       │            │            │               │           │
│  ┌────▼─────────────▼────────────▼───────────────▼──────┐  │
│  │                  Service Layer                        │  │
│  │  AuthService  DocumentService  UserService  RAGService│  │
│  └────┬─────────────────────────────────────────┬───────┘  │
│       │                                         │           │
│  ┌────▼──────────────┐              ┌───────────▼─────────┐ │
│  │   PostgreSQL DB   │              │    Vector Store     │ │
│  │  (SQLAlchemy ORM) │              │  ChromaDB / FAISS   │ │
│  │  Users, Roles,    │              │  Embeddings &       │ │
│  │  Documents        │              │  Chunk Metadata     │ │
│  └───────────────────┘              └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Option 1: Local Setup

#### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Git

#### Step 1: Clone & Setup Environment
```bash
git clone <your-repo-url>
cd financial-doc-management

python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

#### Step 2: Configure Environment
```bash
# Copy the example env file
copy .env.example .env   # Windows
cp .env.example .env     # Linux/macOS

# Edit .env with your values:
# - DATABASE_URL (your PostgreSQL connection string)
# - SECRET_KEY (run: python -c "import secrets; print(secrets.token_hex(32))")
# - OPENAI_API_KEY (optional, only if using OpenAI embeddings)
```

#### Step 3: Create PostgreSQL Database
```bash
# Using psql
psql -U postgres
CREATE DATABASE financial_docs;
\q
```

#### Step 4: Initialize Database
The database tables are created automatically on first startup via SQLAlchemy.
To use Alembic for migration-based setup (recommended for production):

```bash
# Generate initial migration
alembic revision --autogenerate -m "initial_schema"

# Apply migrations
alembic upgrade head
```

#### Step 5: Seed Default Roles
```bash
# Option 1: Via the seeder script
python scripts/seed_sample_data.py

# Option 2: Via the API (after starting the server)
curl -X POST http://localhost:8000/api/v1/auth/seed-roles
```

#### Step 6: Start the Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs** for the interactive Swagger documentation.

---




Services started:
- **API**: http://localhost:8000 — Swagger docs at /docs
- **PostgreSQL**: localhost:5432
- **pgAdmin** (optional): http://localhost:5050

```bash
# Start with pgAdmin
docker compose --profile admin up -d
```

---

## 📁 Project Structure

```
financial-doc-management/
├── app/
│   ├── main.py                    # FastAPI app, middleware, route registration
│   ├── core/
│   │   ├── config.py              # Pydantic settings (reads .env)
│   │   ├── security.py            # JWT + bcrypt password utilities
│   │   ├── logging.py             # Loguru structured logging
│   │   └── exceptions.py          # Custom HTTP exception classes
│   ├── db/
│   │   └── session.py             # Async SQLAlchemy engine + get_db dependency
│   ├── models/
│   │   ├── user.py                # User ORM model
│   │   ├── role.py                # Role, Permission, junction tables
│   │   └── document.py            # Document ORM model
│   ├── schemas/
│   │   ├── auth.py                # Register/Login Pydantic schemas
│   │   ├── document.py            # Document CRUD schemas
│   │   └── rag.py                 # RAG/search schemas
│   ├── auth/
│   │   └── dependencies.py        # JWT extraction + RBAC dependencies
│   ├── services/
│   │   ├── auth_service.py        # Registration, login, role seeding
│   │   ├── document_service.py    # File upload, CRUD operations
│   │   ├── user_service.py        # User profile, role assignment
│   │   └── rag_service.py         # Full RAG pipeline orchestration
│   ├── rag/
│   │   ├── chunker.py             # Text extraction + chunking
│   │   ├── embeddings.py          # SentenceTransformers / OpenAI embeddings
│   │   ├── vector_store.py        # ChromaDB / FAISS abstraction
│   │   └── reranker.py            # Cross-encoder reranking
│   ├── routes/
│   │   ├── auth.py                # /auth endpoints
│   │   ├── roles.py               # /roles endpoints
│   │   ├── users.py               # /users endpoints
│   │   ├── documents.py           # /documents endpoints
│   │   └── rag.py                 # /rag endpoints
│   └── utils/
│       └── file_utils.py          # File handling helpers
├── tests/                          # Pytest tests
├── scripts/
│   └── seed_sample_data.py        # Sample data seeder
├── requirements.txt

```

---

## 🔐 Authentication & RBAC

### Roles & Permissions

| Permission | Admin | Analyst | Auditor | Client |
|------------|-------|---------|---------|--------|
| Upload documents | ✅ | ✅ | ❌ | ❌ |
| View documents | ✅ | ✅ | ✅ | ✅ |
| Edit documents | ✅ | ✅ | ❌ | ❌ |
| Delete documents | ✅ | ❌ | ❌ | ❌ |
| Index documents (RAG) | ✅ | ✅ | ❌ | ❌ |
| Semantic search | ✅ | ✅ | ✅ | ✅ |
| Get document context | ✅ | ✅ | ✅ | ❌ |
| Manage users | ✅ | ❌ | ❌ | ❌ |
| Assign roles | ✅ | ❌ | ❌ | ❌ |

### JWT Flow
```
Client → POST /auth/login → {access_token, refresh_token}
Client → GET /api/v1/... + "Authorization: Bearer {access_token}"
Client → POST /auth/refresh + {refresh_token} → new access_token
```

Tokens:
- **Access token**: 30 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Refresh token**: 7 days (configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)

---

## 📄 Document Management APIs

```
POST   /api/v1/documents/upload          Upload a document (multipart/form-data)
GET    /api/v1/documents                  List with filters & pagination
GET    /api/v1/documents/search           Search by metadata fields
GET    /api/v1/documents/{id}             Get document details
PUT    /api/v1/documents/{id}             Update metadata
DELETE /api/v1/documents/{id}             Soft delete
```

**Document Types**: `invoice`, `report`, `contract`, `balance_sheet`, `audit_report`, `tax_filing`, `other`

**Upload Example (curl)**:
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@financial_report.pdf" \
  -F "title=Q4 2024 Financial Report" \
  -F "company_name=Acme Corp" \
  -F "document_type=report" \
  -F "tags=quarterly,2024"
```

---

## 🧠 RAG Pipeline

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    INDEXING PIPELINE                        │
│                                                             │
│  PDF/DOCX/TXT/XLSX                                          │
│       ↓                                                     │
│  pdfplumber / python-docx                                   │
│  (Text Extraction with page numbers)                        │
│       ↓                                                     │
│  LangChain RecursiveCharacterTextSplitter                   │
│  (chunk_size=512, overlap=64)                               │
│       ↓                                                     │
│  SentenceTransformers all-MiniLM-L6-v2                      │
│  (384-dimensional vectors, L2-normalized)                   │
│       ↓                                                     │
│  ChromaDB (cosine similarity index)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     SEARCH PIPELINE                         │
│                                                             │
│  User Query: "debt ratio risk"                              │
│       ↓                                                     │
│  Embed query (same model as indexing)                       │
│       ↓                                                     │
│  ChromaDB: Top-20 most similar chunks (cosine similarity)   │
│       ↓                                                     │
│  CrossEncoder ms-marco-MiniLM-L-6-v2                        │
│  (Re-scores all 20 pairs: query + chunk together)           │
│       ↓                                                     │
│  Top-5 most relevant chunks returned                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Indexing a Document
```bash
# Step 1: Upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@report.pdf" -F "title=Annual Report" -F "company_name=Acme"

# Returns: {"id": 42, "status": "pending", ...}

# Step 2: Index
curl -X POST http://localhost:8000/api/v1/rag/index-document \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"document_id": 42}'

# Returns: {"status": "indexed", "chunk_count": 47, "processing_time_ms": 3210}
```

### Semantic Search
```bash
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "financial risk related to high debt ratio",
    "top_k": 5,
    "rerank": true,
    "company_filter": "Acme Corp"
  }'
```

**Response**:
```json
{
  "query": "financial risk related to high debt ratio",
  "total_chunks_searched": 20,
  "chunks": [
    {
      "chunk_id": "doc_42_chunk_15",
      "document_id": 42,
      "document_title": "Annual Report 2024",
      "company_name": "Acme Corp",
      "document_type": "report",
      "text": "The debt-to-equity ratio increased to 2.4, indicating elevated financial risk...",
      "relevance_score": 0.8723,
      "rerank_score": 4.231,
      "chunk_index": 15,
      "page_number": 12
    }
  ],
  "search_time_ms": 187.3
}
```

---

## 🧪 Testing

```bash
# Install test dependencies (included in requirements.txt)
pip install pytest pytest-asyncio httpx

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pip install pytest-cov
pytest --cov=app --cov-report=html
```

---

## 🗄️ Database Design

### Entity Relationship Diagram
```
users
├── id (PK)
├── email (UNIQUE)
├── full_name
├── hashed_password
├── is_active
├── company
└── created_at

roles
├── id (PK)
├── name (UNIQUE)
├── description
└── is_active

permissions
├── id (PK)
├── name (UNIQUE)
├── resource (document, user, rag, ...)
└── action (upload, view, delete, ...)

user_roles (junction)
├── user_id (FK → users)
└── role_id (FK → roles)

role_permissions (junction)
├── role_id (FK → roles)
└── permission_id (FK → permissions)

documents
├── id (PK)
├── title
├── company_name
├── document_type (ENUM)
├── filename / stored_filename / file_path
├── file_size / mime_type / file_extension
├── status (pending/processing/indexed/failed/deleted)
├── chunk_count
├── uploaded_by (FK → users)
└── created_at / indexed_at
```

---

## 🔧 Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | JWT signing key (use: `openssl rand -hex 32`) |
| `DATABASE_URL` | (required) | PostgreSQL async connection string |
| `VECTOR_DB_TYPE` | `chroma` | `chroma` or `faiss` |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | `sentence_transformers` or `openai` |
| `SENTENCE_TRANSFORMER_MODEL` | `all-MiniLM-L6-v2` | Any HuggingFace model name |
| `CHUNK_SIZE` | `512` | Characters per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap between adjacent chunks |
| `TOP_K_RETRIEVAL` | `20` | Chunks fetched from vector DB |
| `TOP_K_RERANKED` | `5` | Final chunks after reranking |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model |
| `MAX_FILE_SIZE_MB` | `50` | Maximum upload size |

---

## 🚀 Deployment

### Production Checklist
- [ ] Set `DEBUG=false`
- [ ] Generate strong `SECRET_KEY` (openssl rand -hex 32)
- [ ] Use environment-specific DATABASE_URL
- [ ] Configure `ALLOWED_ORIGINS` for your frontend domains
- [ ] Set up PostgreSQL with SSL
- [ ] Mount persistent volume for `UPLOAD_DIR`
- [ ] Mount persistent volume for ChromaDB store
- [ ] Configure log aggregation (e.g., Datadog, CloudWatch)
- [ ] Set up health check monitoring on `/health`

### Scaling

#### Horizontal Scaling (Multiple API instances)
```yaml
# kubernetes/deployment.yaml
spec:
  replicas: 3
  # IMPORTANT: Use Qdrant (not FAISS/local Chroma) for shared vector store
  # IMPORTANT: Use shared file storage (S3/NFS) for uploads
```

**When scaling out:**
1. Switch `VECTOR_DB_TYPE=qdrant` (Qdrant runs as a separate service)
2. Use S3/MinIO for file storage instead of local disk
3. Use Redis for session/cache management
4. Put API behind a load balancer (nginx, AWS ALB)

#### GPU Acceleration
```bash
# requirements-gpu.txt additions
torch==2.3.0+cu121
faiss-gpu==1.7.4
```

Set `device="cuda"` in `reranker.py` and embeddings models.

---

## 📚 API Documentation

Full interactive documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/api/v1/openapi.json

Import `postman_collection.json` into Postman for pre-built requests.

---

## 🤝 Module Explanations

| Module | Purpose |
|--------|---------|
| `app/core/config.py` | Reads all config from `.env` using Pydantic Settings |
| `app/core/security.py` | bcrypt hashing + JWT create/decode |
| `app/auth/dependencies.py` | FastAPI `Depends()` for auth checks |
| `app/rag/chunker.py` | Text extraction (PDF/DOCX) + LangChain splitting |
| `app/rag/embeddings.py` | SentenceTransformers or OpenAI embedding generation |
| `app/rag/vector_store.py` | ChromaDB/FAISS abstraction layer |
| `app/rag/reranker.py` | Cross-encoder reranking for precision |
| `app/services/rag_service.py` | Orchestrates full indexing + search pipeline |

---

*Built with FastAPI • PostgreSQL • SQLAlchemy • LangChain • ChromaDB • SentenceTransformers*
