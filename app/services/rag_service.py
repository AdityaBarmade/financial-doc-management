"""
app/services/rag_service.py — RAG Pipeline Business Logic

Full RAG Pipeline:
  Document Upload
       ↓
  Text Extraction (PDF/DOCX/TXT/XLSX)
       ↓
  Recursive Chunking (LangChain, ~512 tokens)
       ↓
  Embedding Generation (SentenceTransformers / OpenAI)
       ↓
  Vector Storage (ChromaDB / FAISS)
       ↓
  [At Query Time]
  Query Embedding → Vector Search (Top-20) → Cross-Encoder Reranking → Top-5

Key insight extraction uses simple heuristics on chunk text:
- Detects monetary values, percentages, dates
- Extracts company names, ratios, key financial terms
"""

import time
import re
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import NotFoundException, RAGException, BadRequestException
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.rag.chunker import create_chunks, DocumentChunk
from app.rag.embeddings import get_embedding_provider
from app.rag.vector_store import get_vector_store, SearchResult
from app.rag.reranker import get_reranker
from app.schemas.rag import (
    SemanticSearchRequest, SemanticSearchResponse,
    DocumentChunk as DocumentChunkSchema,
    IndexDocumentResponse, DocumentContextResponse, ContextChunk,
)

logger = get_logger(__name__)


class RAGService:
    """
    RAG service orchestrating the indexing and search pipeline.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._embedder = None
        self._vector_store = None
        self._reranker = None

    @property
    def embedder(self):
        if not self._embedder:
            self._embedder = get_embedding_provider()
        return self._embedder

    @property
    def vector_store(self):
        if not self._vector_store:
            self._vector_store = get_vector_store()
        return self._vector_store

    @property
    def reranker(self):
        if not self._reranker:
            self._reranker = get_reranker()
        return self._reranker

    # ─── INDEXING ──────────────────────────────────────────────────────────────

    async def index_document(
        self,
        document_id: int,
        force_reindex: bool = False,
    ) -> IndexDocumentResponse:
        """
        Full indexing pipeline for a document.

        Steps:
        1. Load document from DB
        2. Check if already indexed (skip unless force_reindex)
        3. Extract text from file
        4. Split into chunks
        5. Generate embeddings for all chunks
        6. Store embeddings in vector DB
        7. Update DB status

        Args:
            document_id: Database document ID
            force_reindex: If True, re-index even if already done

        Returns:
            IndexDocumentResponse with status and chunk count
        """
        start_time = time.perf_counter()

        # Load document from DB
        stmt = select(Document).where(
            Document.id == document_id,
            Document.is_active == True,
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        # Check if already indexed
        if doc.status == DocumentStatus.INDEXED and not force_reindex:
            return IndexDocumentResponse(
                document_id=document_id,
                status="already_indexed",
                chunk_count=doc.chunk_count or 0,
                processing_time_ms=0.0,
                message=f"Document already indexed with {doc.chunk_count} chunks. Use force_reindex=true to re-index.",
            )

        # Mark as processing
        doc.status = DocumentStatus.PROCESSING
        await self.db.commit()

        try:
            # Step 1: Remove old vectors if re-indexing
            if force_reindex and doc.status == DocumentStatus.INDEXED:
                self.vector_store.delete_document(document_id)
                logger.info(f"Cleared old chunks for document {document_id}")

            # Step 2: Chunk the document
            doc_metadata = {
                "title": doc.title,
                "company_name": doc.company_name,
                "document_type": doc.document_type.value,
                "document_id": str(document_id),
                "uploaded_by": str(doc.uploaded_by or ""),
            }

            chunks: List[DocumentChunk] = create_chunks(
                document_id=document_id,
                file_path=doc.file_path,
                metadata=doc_metadata,
            )

            if not chunks:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "No text could be extracted from the document"
                await self.db.commit()
                raise RAGException("Text extraction failed — document may be empty or corrupted")

            logger.info(f"Created {len(chunks)} chunks for document {document_id}")

            # Step 3: Generate embeddings in batches
            texts = [chunk.text for chunk in chunks]
            logger.info(f"Generating embeddings for {len(texts)} chunks...")

            batch_size = 64
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_embeddings = self.embedder.embed(batch_texts)
                all_embeddings.extend(batch_embeddings)

            logger.info(f"Generated {len(all_embeddings)} embeddings")

            # Step 4: Store in vector DB
            self.vector_store.add_documents(chunks, all_embeddings)

            # Step 5: Update DB record
            from datetime import datetime, timezone
            doc.status = DocumentStatus.INDEXED
            doc.chunk_count = len(chunks)
            doc.indexed_at = datetime.now(timezone.utc)
            doc.error_message = None
            await self.db.commit()

            processing_time = (time.perf_counter() - start_time) * 1000

            logger.info(
                f"✅ Document {document_id} indexed: {len(chunks)} chunks "
                f"in {processing_time:.0f}ms"
            )

            return IndexDocumentResponse(
                document_id=document_id,
                status="indexed",
                chunk_count=len(chunks),
                processing_time_ms=round(processing_time, 2),
                message=f"Successfully indexed {len(chunks)} chunks",
            )

        except RAGException:
            raise
        except Exception as e:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            await self.db.commit()
            logger.error(f"Indexing failed for document {document_id}: {e}", exc_info=True)
            raise RAGException(f"Indexing failed: {str(e)}")

    async def remove_from_index(self, document_id: int) -> dict:
        """
        Remove a document's vectors from the vector store.

        Args:
            document_id: Database document ID

        Returns:
            dict with deleted chunk count
        """
        stmt = select(Document).where(Document.id == document_id)
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        deleted_count = self.vector_store.delete_document(document_id)

        # Update DB status
        doc.status = DocumentStatus.PENDING
        doc.chunk_count = None
        doc.indexed_at = None
        await self.db.commit()

        logger.info(f"Removed {deleted_count} chunks for document {document_id}")
        return {
            "document_id": document_id,
            "deleted_chunks": deleted_count,
            "message": f"Removed {deleted_count} chunks from vector store",
        }

    # ─── SEARCH ────────────────────────────────────────────────────────────────

    async def semantic_search(
        self,
        request: SemanticSearchRequest,
    ) -> SemanticSearchResponse:
        """
        Full semantic search pipeline with optional reranking.

        Pipeline:
        1. Embed the query
        2. Search vector DB for Top-20 similar chunks
        3. Apply metadata filters (company, document type)
        4. Optionally rerank using cross-encoder → Top-5
        5. Enrich results with document metadata from DB

        Args:
            request: SemanticSearchRequest with query and filters

        Returns:
            SemanticSearchResponse with ranked chunks
        """
        start_time = time.perf_counter()

        # Step 1: Embed the query
        query_embedding = self.embedder.embed_single(request.query)

        # Step 2: Build filter dict for vector search
        filters = {}
        if request.company_filter:
            filters["company_name"] = request.company_filter
        if request.document_type_filter:
            filters["document_type"] = request.document_type_filter

        # If searching specific document IDs, we'll filter post-search
        top_k_retrieve = settings.TOP_K_RETRIEVAL  # Fetch 20 before reranking

        # Step 3: Vector similarity search
        results: List[SearchResult] = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k_retrieve,
            filters=filters if filters else None,
        )

        # Filter to specific document IDs if requested
        if request.document_ids:
            results = [r for r in results if r.document_id in request.document_ids]

        total_retrieved = len(results)

        # Step 4: Optional cross-encoder reranking
        if request.rerank and len(results) > 1:
            results = self.reranker.rerank(
                query=request.query,
                candidates=results,
                top_k=request.top_k,
            )
        else:
            results = results[:request.top_k]

        # Step 5: Enrich results with DB metadata
        doc_ids = list({r.document_id for r in results})
        docs_by_id = await self._load_documents_by_ids(doc_ids)

        chunks = []
        for result in results:
            doc = docs_by_id.get(result.document_id)
            rerank_score = result.metadata.get("rerank_score")

            chunks.append(DocumentChunkSchema(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_title=doc.title if doc else f"Document #{result.document_id}",
                company_name=doc.company_name if doc else result.metadata.get("company_name", ""),
                document_type=doc.document_type.value if doc else result.metadata.get("document_type", ""),
                text=result.text,
                relevance_score=round(result.score, 4),
                rerank_score=round(rerank_score, 4) if rerank_score else None,
                chunk_index=result.chunk_index,
                page_number=result.page_number,
                metadata=result.metadata,
            ))

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Search completed: '{request.query[:50]}...' → "
            f"{len(chunks)} results in {elapsed_ms:.0f}ms"
        )

        return SemanticSearchResponse(
            query=request.query,
            total_chunks_searched=total_retrieved,
            chunks=chunks,
            search_time_ms=round(elapsed_ms, 2),
        )

    # ─── CONTEXT RETRIEVAL ─────────────────────────────────────────────────────

    async def get_document_context(
        self,
        document_id: int,
    ) -> DocumentContextResponse:
        """
        Retrieve all chunks for a document with extracted insights.

        Returns ordered chunks and AI-extracted key points from the document.

        Args:
            document_id: Database document ID

        Returns:
            DocumentContextResponse with chunks and insights
        """
        # Load document metadata
        stmt = select(Document).where(
            Document.id == document_id,
            Document.is_active == True,
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()

        if not doc:
            raise NotFoundException("Document")

        if doc.status != DocumentStatus.INDEXED:
            raise BadRequestException(
                f"Document is not indexed yet (status: {doc.status.value}). "
                "Call POST /rag/index-document first."
            )

        # Retrieve all chunks from vector store
        raw_chunks = self.vector_store.get_document_chunks(document_id)

        # Build ContextChunk objects
        context_chunks = []
        for chunk_data in raw_chunks:
            text = chunk_data["text"]
            meta = chunk_data["metadata"]
            index = int(meta.get("chunk_index", 0))
            page = int(meta.get("page_number", 0)) or None
            token_estimate = len(text.split())

            context_chunks.append(ContextChunk(
                chunk_id=chunk_data["chunk_id"],
                chunk_index=index,
                text=text,
                page_number=page,
                char_count=len(text),
                token_estimate=token_estimate,
            ))

        # Sort by chunk index for natural document order
        context_chunks.sort(key=lambda c: c.chunk_index)

        # Extract insights from chunks
        full_text = " ".join(c.text for c in context_chunks)
        insights = self._extract_insights(full_text)
        entities = self._extract_entities(full_text)

        return DocumentContextResponse(
            document_id=document_id,
            document_title=doc.title,
            company_name=doc.company_name,
            document_type=doc.document_type.value,
            total_chunks=len(context_chunks),
            chunks=context_chunks,
            extracted_insights=insights,
            key_entities=entities,
            created_at=doc.created_at,
        )

    # ─── Helpers ───────────────────────────────────────────────────────────────

    async def _load_documents_by_ids(
        self, doc_ids: List[int]
    ) -> Dict[int, Document]:
        """Load multiple documents by ID, returning a dict keyed by ID."""
        if not doc_ids:
            return {}

        stmt = select(Document).where(Document.id.in_(doc_ids))
        docs = (await self.db.execute(stmt)).scalars().all()
        return {doc.id: doc for doc in docs}

    @staticmethod
    def _extract_insights(text: str) -> List[str]:
        """
        Extract key financial insights using regex-based heuristics.

        Looks for:
        - Monetary values (revenue, profit, etc.)
        - Percentage changes
        - Key financial ratios
        - Risk mentions
        """
        insights = []

        # Revenue/profit patterns
        money_pattern = r'\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|M|B|K))?\b'
        money_mentions = re.findall(money_pattern, text, re.IGNORECASE)
        if money_mentions:
            insights.append(f"Monetary values mentioned: {', '.join(set(money_mentions[:5]))}")

        # Percentage changes
        pct_pattern = r'(?:increased?|decreased?|grew?|fell?|rose?|declined?)\s+(?:by\s+)?(\d+(?:\.\d+)?%)'
        pct_matches = re.findall(pct_pattern, text, re.IGNORECASE)
        if pct_matches:
            insights.append(f"Percentage changes: {', '.join(set(pct_matches[:5]))}")

        # Debt/risk mentions
        risk_keywords = ["debt ratio", "liquidity", "solvency", "default risk", "credit risk",
                         "cash flow", "net income", "operating income", "EBITDA", "leverage"]
        found_terms = [kw for kw in risk_keywords if kw.lower() in text.lower()]
        if found_terms:
            insights.append(f"Financial concepts mentioned: {', '.join(found_terms[:8])}")

        # Year mentions
        year_pattern = r'\b(20\d{2})\b'
        years = list(set(re.findall(year_pattern, text)))
        if years:
            insights.append(f"Years referenced: {', '.join(sorted(years))}")

        # Fiscal/quarterly mentions
        if re.search(r'Q[1-4]\s+20\d{2}|fiscal\s+year', text, re.IGNORECASE):
            insights.append("Document contains quarterly or fiscal year data")

        return insights if insights else ["No specific financial insights extracted"]

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        """
        Simple entity extraction using patterns.
        For production, use spaCy or a named-entity recognition model.
        """
        entities = []

        # Company-like patterns (Capitalized multi-word phrases)
        company_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:Inc\.|LLC|Corp\.|Ltd\.|Limited|Group|Holdings)\b'
        companies = list(set(re.findall(company_pattern, text)))
        if companies:
            entities.extend([f"Company: {c}" for c in companies[:5]])

        # Currency amounts
        amount_pattern = r'USD?\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion))?\b'
        amounts = list(set(re.findall(amount_pattern, text, re.IGNORECASE)))
        if amounts:
            entities.extend([f"Amount: {a}" for a in amounts[:5]])

        # Dates
        date_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}\b'
        dates = list(set(re.findall(date_pattern, text)))
        if dates:
            entities.extend([f"Date: {d}" for d in dates[:5]])

        return entities if entities else ["No named entities detected"]
