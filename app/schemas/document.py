"""
app/schemas/document.py — Document Pydantic Schemas

Request/response models for document management APIs.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.document import DocumentType, DocumentStatus


class DocumentMetadata(BaseModel):
    """Metadata fields provided when uploading a document."""
    title: str
    company_name: str
    document_type: DocumentType = DocumentType.OTHER
    description: Optional[str] = None
    tags: Optional[str] = None  # Comma-separated tags

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Title must be at least 3 characters")
        if len(v) > 500:
            raise ValueError("Title must not exceed 500 characters")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Q4 2024 Financial Report",
                "company_name": "Acme Corp",
                "document_type": "report",
                "description": "Quarterly financial results summary",
                "tags": "quarterly,2024,revenue",
            }
        }
    )


class DocumentResponse(BaseModel):
    """Full document metadata returned in API responses."""
    id: int
    title: str
    company_name: str
    document_type: DocumentType
    description: Optional[str]
    tags: Optional[str]
    filename: str
    file_size: int
    mime_type: Optional[str]
    status: DocumentStatus
    chunk_count: Optional[int]
    uploaded_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    indexed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    total: int
    page: int
    page_size: int
    items: List[DocumentResponse]


class DocumentSearchParams(BaseModel):
    """Query parameters for metadata-based document filtering."""
    company_name: Optional[str] = None
    document_type: Optional[DocumentType] = None
    tags: Optional[str] = None
    status: Optional[DocumentStatus] = None
    uploaded_by: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    page_size: int = 20

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Page must be >= 1")
        return v

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("Page size must be between 1 and 100")
        return v


class DocumentUpdateRequest(BaseModel):
    """Request body for updating document metadata."""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    document_type: Optional[DocumentType] = None
