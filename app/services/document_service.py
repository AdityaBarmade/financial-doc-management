"""
app/services/document_service.py — Document Management Business Logic

Handles:
- File upload validation, storage, metadata persistence
- Document listing with pagination and filtering
- Document retrieval and deletion (soft delete)
- File type detection and validation
"""

import os
import uuid
import mimetypes
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import (
    NotFoundException, ForbiddenException,
    FileTooLargeException, UnsupportedFileTypeException, BadRequestException
)
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentMetadata, DocumentSearchParams

logger = get_logger(__name__)


class DocumentService:
    """Business logic for document CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_document(
        self,
        file: UploadFile,
        metadata: DocumentMetadata,
        current_user: User,
    ) -> Document:
        """
        Process and store an uploaded document.

        Steps:
        1. Validate file size and extension
        2. Generate unique filename and save to disk
        3. Create DB record with metadata
        4. Return Document object

        Args:
            file: FastAPI UploadFile object
            metadata: User-provided document metadata
            current_user: Authenticated user (for ownership tracking)

        Raises:
            FileTooLargeException: If file exceeds MAX_FILE_SIZE_MB
            UnsupportedFileTypeException: If extension not in allowed list
        """
        # ─── Validate File Size ────────────────────────────────────────────────
        # Read content to check size (stream is not seekable in all cases)
        content = await file.read()
        file_size = len(content)

        if file_size > settings.max_file_size_bytes:
            raise FileTooLargeException(settings.MAX_FILE_SIZE_MB)

        if file_size == 0:
            raise BadRequestException("Uploaded file is empty")

        # ─── Validate File Extension ───────────────────────────────────────────
        original_filename = file.filename or "unknown"
        ext = os.path.splitext(original_filename)[1].lower()

        if ext not in settings.allowed_extensions_list:
            raise UnsupportedFileTypeException(ext, settings.allowed_extensions_list)

        # ─── Generate Unique Storage Path ──────────────────────────────────────
        file_uuid = str(uuid.uuid4())
        stored_filename = f"{file_uuid}{ext}"

        # Organize files in subdirectories by date
        today = datetime.now().strftime("%Y/%m/%d")
        storage_dir = os.path.join(settings.UPLOAD_DIR, today)
        os.makedirs(storage_dir, exist_ok=True)

        file_path = os.path.join(storage_dir, stored_filename)

        # ─── Save File to Disk ─────────────────────────────────────────────────
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(
            f"File saved: {original_filename} → {file_path} "
            f"({file_size / 1024:.1f} KB)"
        )

        # ─── Detect MIME Type ──────────────────────────────────────────────────
        mime_type, _ = mimetypes.guess_type(original_filename)

        # ─── Create DB Record ──────────────────────────────────────────────────
        document = Document(
            title=metadata.title,
            description=metadata.description,
            company_name=metadata.company_name,
            document_type=metadata.document_type,
            tags=metadata.tags,
            filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_extension=ext,
            status=DocumentStatus.PENDING,
            uploaded_by=current_user.id,
        )

        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)

        logger.info(
            f"Document record created: id={document.id}, "
            f"title='{document.title}', user={current_user.email}"
        )
        return document

    async def get_document(self, document_id: int, current_user: User) -> Document:
        """
        Retrieve a document by ID.

        Raises:
            NotFoundException: If document doesn't exist
        """
        stmt = select(Document).where(
            Document.id == document_id,
            Document.is_active == True,
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        return doc

    async def list_documents(
        self,
        params: DocumentSearchParams,
        current_user: User,
    ) -> dict:
        """
        List documents with optional metadata filtering and pagination.

        Returns:
            dict with total count, page info, and items list
        """
        stmt = select(Document).where(Document.is_active == True)

        # ─── Apply Filters ─────────────────────────────────────────────────────
        if params.company_name:
            stmt = stmt.where(
                Document.company_name.ilike(f"%{params.company_name}%")
            )
        if params.document_type:
            stmt = stmt.where(Document.document_type == params.document_type)
        if params.status:
            stmt = stmt.where(Document.status == params.status)
        if params.uploaded_by:
            stmt = stmt.where(Document.uploaded_by == params.uploaded_by)
        if params.tags:
            stmt = stmt.where(Document.tags.ilike(f"%{params.tags}%"))
        if params.date_from:
            stmt = stmt.where(Document.created_at >= params.date_from)
        if params.date_to:
            stmt = stmt.where(Document.created_at <= params.date_to)

        # ─── Count Total ───────────────────────────────────────────────────────
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # ─── Apply Pagination ──────────────────────────────────────────────────
        offset = (params.page - 1) * params.page_size
        stmt = (
            stmt
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(params.page_size)
        )

        docs = (await self.db.execute(stmt)).scalars().all()

        return {
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "items": list(docs),
        }

    async def delete_document(
        self,
        document_id: int,
        current_user: User,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a document (soft delete by default).

        Soft delete: Sets is_active=False, preserves file and DB record
        Hard delete: Removes file from disk and marks as deleted

        Raises:
            NotFoundException: If document doesn't exist
            ForbiddenException: If non-admin tries to delete another user's doc
        """
        stmt = select(Document).where(
            Document.id == document_id,
            Document.is_active == True,
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        # Non-admins can only delete their own documents
        if (
            "admin" not in current_user.role_names
            and doc.uploaded_by != current_user.id
        ):
            raise ForbiddenException("You can only delete your own documents")

        if hard_delete:
            # Remove physical file
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
                logger.info(f"Deleted file: {doc.file_path}")

        # Soft delete
        doc.is_active = False
        doc.status = DocumentStatus.DELETED
        await self.db.commit()

        logger.info(
            f"Document {document_id} deleted by {current_user.email} "
            f"(hard={hard_delete})"
        )
        return True

    async def update_document(
        self,
        document_id: int,
        update_data: dict,
        current_user: User,
    ) -> Document:
        """
        Update document metadata fields.

        Raises:
            NotFoundException: If document doesn't exist
            ForbiddenException: If user doesn't own the document and isn't admin/analyst
        """
        stmt = select(Document).where(
            Document.id == document_id,
            Document.is_active == True,
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        allowed_roles = ["admin", "analyst"]
        if (
            not any(r in current_user.role_names for r in allowed_roles)
            and doc.uploaded_by != current_user.id
        ):
            raise ForbiddenException("Insufficient permissions to edit this document")

        # Apply updates
        for field, value in update_data.items():
            if value is not None and hasattr(doc, field):
                setattr(doc, field, value)

        await self.db.commit()
        await self.db.refresh(doc)
        return doc
