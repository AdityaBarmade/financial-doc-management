"""
app/rag/reranker.py — Cross-Encoder Reranking System

Pipeline:
  Query + Top-20 Chunks → Cross-Encoder → Scored pairs → Top-5

Why rerank?
- Bi-encoder (embedding) retrieval is approximate; optimized for speed
- Cross-encoders see query+document together → much more accurate scoring
- Significantly improves precision of final results

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
- Very fast (MiniLM architecture)
- Trained on MS MARCO (passage retrieval dataset)
- Produces a single relevance score per (query, passage) pair
"""

from typing import List, Tuple
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.vector_store import SearchResult

logger = get_logger(__name__)


class CrossEncoderReranker:
    """
    Cross-encoder based reranker using SentenceTransformers.

    The cross-encoder reads both the query and candidate text simultaneously
    using a single BERT-like model — this is much more accurate than comparing
    query and document embeddings separately.

    Usage:
        reranker = CrossEncoderReranker()
        reranked = reranker.rerank(query, candidates, top_k=5)
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.RERANKER_MODEL
        self._model = None

    def _load_model(self):
        """Lazy-load cross-encoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading CrossEncoder model: {self.model_name}")
            self._model = CrossEncoder(
                self.model_name,
                max_length=512,
                device="cpu",  # Change to "cuda" if GPU available
            )
            logger.info("✅ CrossEncoder model loaded")
        return self._model

    def rerank(
        self,
        query: str,
        candidates: List[SearchResult],
        top_k: int = None,
    ) -> List[SearchResult]:
        """
        Rerank candidate chunks using cross-encoder scores.

        Args:
            query: The search query string
            candidates: Top-K results from vector search (typically 20)
            top_k: How many results to return after reranking (default from settings)

        Returns:
            Reranked list of SearchResult, truncated to top_k
        """
        top_k = top_k or settings.TOP_K_RERANKED

        if not candidates:
            return []

        if len(candidates) == 1:
            return candidates

        model = self._load_model()

        # Build (query, text) pairs for cross-encoder
        pairs = [(query, result.text) for result in candidates]

        # Score all pairs in a single batch
        scores = model.predict(pairs, batch_size=32, show_progress_bar=False)

        # Attach rerank scores and sort descending
        scored_candidates = []
        for result, score in zip(candidates, scores):
            # Create new result with rerank score attached
            result_with_score = SearchResult(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=result.text,
                score=result.score,           # Original similarity score
                chunk_index=result.chunk_index,
                page_number=result.page_number,
                metadata={**result.metadata, "rerank_score": float(score)},
            )
            scored_candidates.append((result_with_score, float(score)))

        # Sort by rerank score (higher = more relevant)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Return top_k results
        reranked = [item[0] for item in scored_candidates[:top_k]]

        logger.info(
            f"Reranked {len(candidates)} candidates → top {len(reranked)} results"
        )
        return reranked

    def score_single(self, query: str, text: str) -> float:
        """Score a single (query, text) pair."""
        model = self._load_model()
        score = model.predict([(query, text)])
        return float(score[0])


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    """Cached reranker instance — loads model only once."""
    return CrossEncoderReranker()
