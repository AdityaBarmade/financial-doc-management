"""
app/schemas/rag.py — RAG / Semantic Search Pydantic Schemas

Request/response models for RAG pipeline APIs.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator


class SemanticSearchRequest(BaseModel):
    """Request body for POST /rag/search."""
    query: str
    top_k: Optional[int] = 5
    document_ids: Optional[List[int]] = None      # Scope search to specific docs
    company_filter: Optional[str] = None           # Filter by company
    document_type_filter: Optional[str] = None     # Filter by document type
    rerank: bool = True                            # Whether to apply cross-encoder reranker

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Query must be at least 3 characters")
        if len(v) > 2000:
            raise ValueError("Query must not exceed 2000 characters")
        return v

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: Optional[int]) -> int:
        if v is None:
            return 5
        if v < 1 or v > 20:
            raise ValueError("top_k must be between 1 and 20")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "financial risk related to high debt ratio",
                "top_k": 5,
                "rerank": True,
            }
        }
    )


class DocumentChunk(BaseModel):
    """A single text chunk from a document with relevance metadata."""
    chunk_id: str
    document_id: int
    document_title: str
    company_name: str
    document_type: str
    text: str                     # The actual chunk text
    relevance_score: float        # Similarity score (0-1)
    rerank_score: Optional[float] = None  # Cross-encoder reranker score
    chunk_index: int              # Position of chunk in document
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = {}


class SemanticSearchResponse(BaseModel):
    """Response from POST /rag/search."""
    query: str
    total_chunks_searched: int
    chunks: List[DocumentChunk]
    search_time_ms: float


class IndexDocumentRequest(BaseModel):
    """Request body for POST /rag/index-document."""
    document_id: int
    force_reindex: bool = False   # Re-process even if already indexed

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"document_id": 42, "force_reindex": False}
        }
    )


class IndexDocumentResponse(BaseModel):
    """Response from POST /rag/index-document."""
    document_id: int
    status: str                   # "indexed" | "already_indexed" | "failed"
    chunk_count: int
    processing_time_ms: float
    message: str


class ContextChunk(BaseModel):
    """A chunk with additional context info for GET /rag/context/{doc_id}."""
    chunk_id: str
    chunk_index: int
    text: str
    page_number: Optional[int] = None
    char_count: int
    token_estimate: int


class DocumentContextResponse(BaseModel):
    """Response from GET /rag/context/{document_id}."""
    document_id: int
    document_title: str
    company_name: str
    document_type: str
    total_chunks: int
    chunks: List[ContextChunk]
    extracted_insights: List[str]     # Key insights extracted from document
    key_entities: List[str]           # Named entities (companies, dates, amounts)
    created_at: datetime


class RoleCreateRequest(BaseModel):
    """Request body for POST /roles/create."""
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 2:
            raise ValueError("Role name must be at least 2 characters")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "reviewer", "description": "Can review documents"}
        }
    )


class RoleResponse(BaseModel):
    """Role data returned in API responses."""
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    permissions: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class AssignRoleRequest(BaseModel):
    """Request body for POST /users/assign-role."""
    user_id: int
    role_name: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"user_id": 5, "role_name": "analyst"}
        }
    )
