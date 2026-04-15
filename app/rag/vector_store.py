"""
app/rag/vector_store.py — Vector Database Abstraction Layer

Supports multiple backends selectable via VECTOR_DB_TYPE env var:
- chroma:  ChromaDB (persistent local, recommended for dev)
- faiss:   FAISS (in-memory, fast, no persistence)
- qdrant:  Qdrant (production vector DB with filtering)

All backends implement the same interface:
- add_documents(chunks, embeddings, metadata)
- search(query_embedding, top_k, filters)
- delete_document(document_id)
- get_document_chunks(document_id)
"""

from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.chunker import DocumentChunk

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """A single result from vector similarity search."""
    chunk_id: str
    document_id: int
    text: str
    score: float          # Cosine similarity (0 to 1)
    chunk_index: int
    page_number: Optional[int]
    metadata: Dict[str, Any]


# ─── ChromaDB Backend ─────────────────────────────────────────────────────────

class ChromaVectorStore:
    """
    ChromaDB-based vector store with persistence.

    Collections use L2 distance metric (converted to similarity in results).
    Supports metadata filtering (company_name, document_type, etc.)
    """

    COLLECTION_NAME = "financial_documents"

    def __init__(self):
        self._client = None
        self._collection = None

    def _init(self):
        """Lazy initialize ChromaDB client and collection."""
        if self._client is not None:
            return

        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIRECTORY,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Get or create the collection
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # Use cosine similarity
        )
        logger.info(f"ChromaDB collection '{self.COLLECTION_NAME}' ready")

    def add_documents(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
    ) -> None:
        """
        Store chunks with their embeddings.

        Args:
            chunks: List of DocumentChunk objects
            embeddings: Corresponding embedding vectors
        """
        self._init()

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [
            {
                **chunk.metadata,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number or 0,
                "document_id": str(chunk.document_id),
                "char_count": chunk.char_count,
            }
            for chunk in chunks
        ]

        # Upsert (insert or update) to handle re-indexing
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Stored {len(chunks)} chunks in ChromaDB")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Perform vector similarity search.

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filters: Metadata filters (e.g., {"document_id": "42"})

        Returns:
            Sorted list of SearchResult (highest similarity first)
        """
        self._init()

        where_clause = None
        if filters:
            # Build ChromaDB where clause
            conditions = []
            for key, value in filters.items():
                conditions.append({key: {"$eq": str(value)}})
            where_clause = {"$and": conditions} if len(conditions) > 1 else conditions[0]

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count() or 1),
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        search_results = []
        if not results["ids"][0]:
            return search_results

        for i, chunk_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            # ChromaDB uses L2 distance; convert to similarity (0-1)
            distance = results["distances"][0][i]
            similarity = max(0.0, 1.0 - distance)

            search_results.append(SearchResult(
                chunk_id=chunk_id,
                document_id=int(meta.get("document_id", 0)),
                text=results["documents"][0][i],
                score=similarity,
                chunk_index=int(meta.get("chunk_index", 0)),
                page_number=int(meta.get("page_number", 0)) or None,
                metadata=meta,
            ))

        return sorted(search_results, key=lambda r: r.score, reverse=True)

    def delete_document(self, document_id: int) -> int:
        """Remove all chunks belonging to a document. Returns count deleted."""
        self._init()

        # Find all chunk IDs for this document
        results = self._collection.get(
            where={"document_id": {"$eq": str(document_id)}},
            include=[],
        )

        if not results["ids"]:
            return 0

        self._collection.delete(ids=results["ids"])
        count = len(results["ids"])
        logger.info(f"Deleted {count} chunks for document {document_id} from ChromaDB")
        return count

    def get_document_chunks(self, document_id: int) -> List[Dict[str, Any]]:
        """Get all chunks for a specific document."""
        self._init()

        results = self._collection.get(
            where={"document_id": {"$eq": str(document_id)}},
            include=["documents", "metadatas"],
        )

        chunks = []
        for i, chunk_id in enumerate(results["ids"]):
            chunks.append({
                "chunk_id": chunk_id,
                "text": results["documents"][i],
                "metadata": results["metadatas"][i],
            })

        # Sort by chunk_index for natural document order
        return sorted(chunks, key=lambda c: int(c["metadata"].get("chunk_index", 0)))


# ─── FAISS Backend ────────────────────────────────────────────────────────────

class FAISSVectorStore:
    """
    FAISS-based in-memory vector store.

    Fast, no external dependencies, but:
    - Data is NOT persisted between restarts
    - No native metadata filtering (done in-memory post search)

    Best for: development, testing, small datasets
    """

    def __init__(self):
        self._index = None
        self._id_to_data: Dict[str, Dict] = {}  # chunk_id → data
        self._embeddings_list: List[List[float]] = []
        self._ids_list: List[str] = []
        self._dim = None

    def _init_index(self, dim: int):
        """Initialize FAISS flat index for cosine similarity."""
        if self._index is None:
            import faiss
            self._dim = dim
            # IndexFlatIP = Inner Product (dot product, ~cosine for normalized vectors)
            self._index = faiss.IndexFlatIP(dim)
            logger.info(f"FAISS index initialized (dim={dim})")

    def add_documents(self, chunks: List[DocumentChunk], embeddings: List[List[float]]) -> None:
        import numpy as np
        import faiss

        if not embeddings:
            return

        arr = np.array(embeddings, dtype=np.float32)
        # Normalize for cosine similarity
        faiss.normalize_L2(arr)

        self._init_index(arr.shape[1])
        self._index.add(arr)

        for chunk, emb in zip(chunks, embeddings):
            self._id_to_data[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "metadata": chunk.metadata,
            }
            self._ids_list.append(chunk.chunk_id)

        logger.info(f"FAISS: added {len(chunks)} vectors (total: {self._index.ntotal})")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []

        import numpy as np
        import faiss

        q = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(q)

        k = min(top_k * 5, self._index.ntotal)  # Fetch more to allow filtering
        scores, indices = self._index.search(q, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk_id = self._ids_list[idx]
            data = self._id_to_data.get(chunk_id)
            if not data:
                continue

            # Apply metadata filters
            if filters:
                match = all(
                    str(data["metadata"].get(k)) == str(v)
                    for k, v in filters.items()
                )
                if not match:
                    continue

            results.append(SearchResult(
                chunk_id=chunk_id,
                document_id=data["document_id"],
                text=data["text"],
                score=float(score),
                chunk_index=data["chunk_index"],
                page_number=data["page_number"],
                metadata=data["metadata"],
            ))

            if len(results) >= top_k:
                break

        return results

    def delete_document(self, document_id: int) -> int:
        """FAISS doesn't support deletion; mark as deleted in metadata."""
        count = 0
        for chunk_id, data in list(self._id_to_data.items()):
            if data["document_id"] == document_id:
                del self._id_to_data[chunk_id]
                count += 1
        return count

    def get_document_chunks(self, document_id: int) -> List[Dict[str, Any]]:
        return [
            data for data in self._id_to_data.values()
            if data["document_id"] == document_id
        ]


# ─── Vector Store Factory ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore | FAISSVectorStore:
    """
    Factory that returns the configured vector store singleton.
    Cached — only one instance exists per process.
    """
    db_type = settings.VECTOR_DB_TYPE.lower()

    if db_type == "chroma":
        logger.info("Initializing ChromaDB vector store")
        return ChromaVectorStore()
    elif db_type == "faiss":
        logger.info("Initializing FAISS vector store")
        return FAISSVectorStore()
    else:
        raise ValueError(f"Unsupported VECTOR_DB_TYPE: {db_type}. Use 'chroma' or 'faiss'")
