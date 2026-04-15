"""
app/routes/documents.py — Document Management Endpoints

POST   /documents/upload          - Upload a financial document
GET    /documents                  - List documents (with filtering)
GET    /documents/search           - Search documents by metadata
GET    /documents/{document_id}   - Get document details
PUT    /documents/{document_id}   - Update document metadata
DELETE /documents/{document_id}   - Delete a document
"""

from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.dependencies import (
    get_current_user_with_roles,
    require_permission,
    require_roles,
)
from app.models.document import DocumentType, DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DocumentResponse, DocumentListResponse,
    DocumentMetadata, DocumentSearchParams, DocumentUpdateRequest
)
from app.services.document_service import DocumentService

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a financial document",
    description="""
Upload a financial document with metadata.

**Supported formats**: PDF, DOCX, TXT, XLSX, CSV

**Roles**: Admin, Analyst

After uploading, call `POST /rag/index-document` to make the document
searchable via semantic search.
""",
)
async def upload_document(
    file: UploadFile = File(..., description="Financial document file"),
    title: str = Form(..., description="Document title"),
    company_name: str = Form(..., description="Company name"),
    document_type: DocumentType = Form(DocumentType.OTHER, description="Document type"),
    description: Optional[str] = Form(None, description="Optional description"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "upload")),
) -> DocumentResponse:
    metadata = DocumentMetadata(
        title=title,
        company_name=company_name,
        document_type=document_type,
        description=description,
        tags=tags,
    )
    service = DocumentService(db)
    doc = await service.upload_document(file, metadata, current_user)
    return DocumentResponse.model_validate(doc)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Paginated list with optional metadata filters.",
)
async def list_documents(
    company_name: Optional[str] = Query(None, description="Filter by company name"),
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type"),
    tags: Optional[str] = Query(None, description="Filter by tag"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by processing status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "view")),
) -> DocumentListResponse:
    params = DocumentSearchParams(
        company_name=company_name,
        document_type=document_type,
        tags=tags,
        status=status,
        page=page,
        page_size=page_size,
    )
    service = DocumentService(db)
    result = await service.list_documents(params, current_user)

    return DocumentListResponse(
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        items=[DocumentResponse.model_validate(doc) for doc in result["items"]],
    )


@router.get(
    "/search",
    response_model=DocumentListResponse,
    summary="Search documents by metadata",
    description="""
Filter documents by metadata fields.

For **semantic/AI search**, use `POST /rag/search` instead.
This endpoint only searches metadata (title, company, type, etc.).
""",
)
async def search_documents(
    q: Optional[str] = Query(None, description="Search in title/description"),
    company_name: Optional[str] = Query(None),
    document_type: Optional[DocumentType] = Query(None),
    uploaded_by: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "view")),
) -> DocumentListResponse:
    params = DocumentSearchParams(
        company_name=company_name or q,
        document_type=document_type,
        uploaded_by=uploaded_by,
        page=page,
        page_size=page_size,
    )
    service = DocumentService(db)
    result = await service.list_documents(params, current_user)

    return DocumentListResponse(
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        items=[DocumentResponse.model_validate(doc) for doc in result["items"]],
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "view")),
) -> DocumentResponse:
    service = DocumentService(db)
    doc = await service.get_document(document_id, current_user)
    return DocumentResponse.model_validate(doc)


@router.put(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Update document metadata",
    description="Update title, description, tags, or document type. **Admin or Analyst.**",
)
async def update_document(
    document_id: int,
    data: DocumentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "edit")),
) -> DocumentResponse:
    service = DocumentService(db)
    update_dict = data.model_dump(exclude_none=True)
    doc = await service.update_document(document_id, update_dict, current_user)
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document",
    description="""
Soft-delete a document (sets is_active=False).

Also removes the document from the vector store if it was indexed.

**Roles**: Admin (any document), Analyst (own documents only)
""",
)
async def delete_document(
    document_id: int,
    hard_delete: bool = Query(False, description="Also delete file from disk"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "delete")),
):
    from app.rag.vector_store import get_vector_store
    service = DocumentService(db)

    # Remove from vector store first
    try:
        vs = get_vector_store()
        deleted_chunks = vs.delete_document(document_id)
    except Exception:
        deleted_chunks = 0

    await service.delete_document(document_id, current_user, hard_delete=hard_delete)

    return {
        "message": f"Document {document_id} deleted successfully",
        "vector_chunks_removed": deleted_chunks,
    }
