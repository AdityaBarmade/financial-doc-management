"""
app/models/document.py — Document ORM Model

Table: documents
- Stores metadata for uploaded financial documents
- File content is stored on disk; DB holds path + metadata
- Vector embeddings stored separately in vector DB (Chroma/FAISS)
"""

import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, Enum, BigInteger
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class DocumentType(str, enum.Enum):
    """Allowed financial document types."""
    INVOICE = "invoice"
    REPORT = "report"
    CONTRACT = "contract"
    BALANCE_SHEET = "balance_sheet"
    AUDIT_REPORT = "audit_report"
    TAX_FILING = "tax_filing"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    """Processing status of a document."""
    PENDING = "pending"         # Uploaded, not yet indexed
    PROCESSING = "processing"   # Being chunked/embedded
    INDEXED = "indexed"         # In vector DB, searchable
    FAILED = "failed"           # Processing failed
    DELETED = "deleted"         # Soft deleted


class Document(Base):
    """
    Financial document metadata model.

    The actual file is stored at: uploads/{document_id}/{filename}
    The vector embeddings are stored in the configured vector DB.

    Relationships:
    - uploaded_by_user: Many-to-one with User
    """
    __tablename__ = "documents"

    # ─── Primary Key ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ─── Metadata ─────────────────────────────────────────────────────────────
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    company_name = Column(String(255), nullable=False, index=True)
    document_type = Column(
        Enum(DocumentType, native_enum=False),
        nullable=False,
        default=DocumentType.OTHER,
        index=True,
    )
    tags = Column(Text, nullable=True)  # Comma-separated tags for filtering

    # ─── File Info ────────────────────────────────────────────────────────────
    filename = Column(String(500), nullable=False)          # Original filename
    stored_filename = Column(String(500), nullable=False)   # UUID-based stored name
    file_path = Column(Text, nullable=False)                # Full disk path
    file_size = Column(BigInteger, nullable=False)          # Bytes
    mime_type = Column(String(100), nullable=True)
    file_extension = Column(String(20), nullable=False)

    # ─── Processing ───────────────────────────────────────────────────────────
    status = Column(
        Enum(DocumentStatus, native_enum=False),
        nullable=False,
        default=DocumentStatus.PENDING,
        index=True,
    )
    chunk_count = Column(Integer, nullable=True)            # Number of chunks created
    error_message = Column(Text, nullable=True)             # If status=FAILED
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    # ─── Ownership ────────────────────────────────────────────────────────────
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # ─── Timestamps ───────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, default=True, nullable=False)  # Soft delete flag

    # ─── Relationships ────────────────────────────────────────────────────────
    uploaded_by_user = relationship("User", back_populates="documents")

    def __repr__(self):
        return f"<Document id={self.id} title={self.title!r} type={self.document_type}>"
