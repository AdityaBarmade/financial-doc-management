"""
FastAPI Financial Document Management System
Entry point: app/main.py

Bootstraps the FastAPI application with:
- CORS middleware
- Route registration
- Lifespan events (DB init, vector store init)
- Swagger/OpenAPI configuration
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import init_db
from app.rag.vector_store import get_vector_store
from app.routes import auth, documents, rag, roles, users

# ─── Logging Setup ────────────────────────────────────────────────────────────
setup_logging()
logger = get_logger(__name__)


# ─── Lifespan (Startup / Shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info("🚀 Starting Financial Document Management System...")

    # Create upload & log directories first
    import os
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
    logger.info("✅ Storage directories ready")

    # Initialize database tables
    await init_db()
    logger.info("✅ Database initialized")

    # Seed default roles and permissions (idempotent)
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import AuthService
    async with AsyncSessionLocal() as db:
        await AuthService.seed_default_roles(db)
    logger.info("✅ Default roles seeded")

    # Initialize vector store (creates collection if not exists)
    vs = get_vector_store()
    logger.info(f"✅ Vector store '{settings.VECTOR_DB_TYPE}' initialized")

    yield  # Application runs here

    logger.info("🛑 Shutting down application...")


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## 📊 Financial Document Management System

A scalable backend for managing financial documents with **AI-powered semantic search**.

### Key Features
- 🔐 JWT Authentication with RBAC (Admin, Analyst, Auditor, Client)
- 📄 Document upload & management (PDF, DOCX, XLSX, TXT)
- 🧠 RAG pipeline: chunking → embeddings → vector search → reranking
- 🔍 Semantic search across all indexed documents
- 📊 Context retrieval with AI-extracted insights

### Roles & Permissions
| Role | Upload | Edit | Delete | View | Admin |
|------|--------|------|--------|------|-------|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ |
| Analyst | ✅ | ✅ | ❌ | ✅ | ❌ |
| Auditor | ❌ | ❌ | ❌ | ✅ | ❌ |
| Client | ❌ | ❌ | ❌ | ✅ | ❌ |
    """,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS Middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Global Exception Handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please contact support."},
    )


# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["🔐 Authentication"])
app.include_router(roles.router, prefix=f"{settings.API_V1_PREFIX}/roles", tags=["👥 Roles"])
app.include_router(users.router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["👤 Users"])
app.include_router(documents.router, prefix=f"{settings.API_V1_PREFIX}/documents", tags=["📄 Documents"])
app.include_router(rag.router, prefix=f"{settings.API_V1_PREFIX}/rag", tags=["🧠 RAG / Semantic Search"])


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["📡 Health"])
async def health_check():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "vector_db": settings.VECTOR_DB_TYPE,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
    }


@app.get("/", tags=["📡 Health"])
async def root():
    """Root endpoint with system info."""
    return {
        "message": "Welcome to the Financial Document Management System",
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }
