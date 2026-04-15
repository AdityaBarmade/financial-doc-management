"""
app/routes/rag.py — RAG / Semantic Search Endpoints

POST /rag/index-document            - Index a document into vector store
DELETE /rag/remove-document/{id}   - Remove document from vector store
POST /rag/search                    - Semantic search across all indexed docs
GET  /rag/context/{document_id}     - Get document chunks + insights
GET  /rag/status                    - Vector store statistics
"""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import (
    get_current_user_with_roles,
    require_permission,
    require_roles,
)
from app.models.user import User
from app.schemas.rag import (
    SemanticSearchRequest, SemanticSearchResponse,
    IndexDocumentRequest, IndexDocumentResponse,
    DocumentContextResponse,
)
from app.services.rag_service import RAGService

router = APIRouter()


@router.post(
    "/index-document",
    response_model=IndexDocumentResponse,
    summary="Index a document for semantic search",
    description="""
Process and index a document into the vector store.

**Pipeline**:
1. Load document from disk
2. Extract text (PDF/DOCX/TXT/XLSX)
3. Split into ~512-character chunks
4. Generate embeddings (SentenceTransformers or OpenAI)
5. Store vectors in ChromaDB/FAISS

**After indexing**, the document becomes searchable via `POST /rag/search`.

**Roles**: Admin, Analyst
""",
)
async def index_document(
    data: IndexDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag", "index")),
) -> IndexDocumentResponse:
    service = RAGService(db)
    return await service.index_document(
        document_id=data.document_id,
        force_reindex=data.force_reindex,
    )


@router.delete(
    "/remove-document/{document_id}",
    summary="Remove document from vector store",
    description="""
Remove all vector embeddings for a document from the vector store.
The document record in PostgreSQL is NOT deleted — only the vectors.

To re-index, call `POST /rag/index-document` again.

**Roles**: Admin, Analyst
""",
)
async def remove_document(
    document_id: int = Path(..., description="Document ID to remove from vector store"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag", "index")),
):
    service = RAGService(db)
    return await service.remove_from_index(document_id)


@router.post(
    "/search",
    response_model=SemanticSearchResponse,
    summary="Semantic search across documents",
    description="""
Perform AI-powered semantic search using embeddings + reranking.

## Pipeline
```
Query Text
   ↓
Embed (SentenceTransformers/OpenAI)
   ↓
Vector Search — Top 20 most similar chunks
   ↓
Cross-Encoder Reranking (optional) — Top 5 most relevant
   ↓
Enriched Results
```

## Filters
- `document_ids`: Scope to specific documents
- `company_filter`: Filter by company name
- `document_type_filter`: Filter by document type
- `rerank`: Set to false to skip reranking (faster but less accurate)

**Example**: Find all chunks about "debt ratio risk" across all indexed documents.
""",
)
async def semantic_search(
    request: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag", "search")),
) -> SemanticSearchResponse:
    service = RAGService(db)
    return await service.semantic_search(request)


@router.get(
    "/context/{document_id}",
    response_model=DocumentContextResponse,
    summary="Get document chunks and insights",
    description="""
Retrieve all indexed chunks for a document, along with automatically
extracted financial insights and named entities.

The document must be indexed (`status=indexed`) before calling this endpoint.

**Roles**: Admin, Analyst, Auditor
""",
)
async def get_document_context(
    document_id: int = Path(..., description="Document ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag", "context")),
) -> DocumentContextResponse:
    service = RAGService(db)
    return await service.get_document_context(document_id)


@router.get(
    "/status",
    summary="Vector store statistics",
    description="Get information about the vector store (collection count, type, etc.)",
)
async def vector_store_status(
    current_user: User = Depends(get_current_user_with_roles),
):
    from app.rag.vector_store import get_vector_store
    from app.core.config import settings

    vs = get_vector_store()
    info = {
        "vector_db_type": settings.VECTOR_DB_TYPE,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": (
            settings.SENTENCE_TRANSFORMER_MODEL
            if settings.EMBEDDING_PROVIDER == "sentence_transformers"
            else settings.OPENAI_EMBEDDING_MODEL
        ),
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "top_k_retrieval": settings.TOP_K_RETRIEVAL,
        "top_k_reranked": settings.TOP_K_RERANKED,
        "reranker_model": settings.RERANKER_MODEL,
    }

    # Try to get chunk count from ChromaDB
    if settings.VECTOR_DB_TYPE == "chroma" and hasattr(vs, "_collection") and vs._collection:
        try:
            info["total_chunks"] = vs._collection.count()
        except Exception:
            info["total_chunks"] = "unavailable"
    elif settings.VECTOR_DB_TYPE == "faiss" and hasattr(vs, "_index") and vs._index:
        info["total_chunks"] = vs._index.ntotal

    return info
