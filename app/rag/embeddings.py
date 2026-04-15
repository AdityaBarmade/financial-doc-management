"""
app/rag/embeddings.py — Embedding Provider

Supports two providers:
1. SentenceTransformers (local, free, default)
2. OpenAI text-embedding models (cloud, requires API key)

Both implement the same interface: embed(texts) → List[List[float]]
"""

from typing import List, Union
import numpy as np
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SentenceTransformerEmbeddings:
    """
    Local embedding provider using SentenceTransformers.

    Default model: all-MiniLM-L6-v2
    - 384-dimensional vectors
    - ~80MB model size
    - Runs on CPU efficiently

    For higher quality: use 'all-mpnet-base-v2' (768-dim, slower)
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.SENTENCE_TRANSFORMER_MODEL
        self._model = None

    def _load_model(self):
        """Lazy-load the model on first use to avoid startup delays."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info("✅ SentenceTransformer model loaded")
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each a list of floats)
        """
        model = self._load_model()
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
        )
        return embeddings.tolist()

    def embed_single(self, text: str) -> List[float]:
        """Embed a single text string."""
        return self.embed([text])[0]

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension for this model."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


class OpenAIEmbeddings:
    """
    Cloud embedding provider using OpenAI's embedding API.

    Model: text-embedding-3-small (1536-dim) or text-embedding-3-large (3072-dim)
    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.OPENAI_EMBEDDING_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings via OpenAI API.
        Batches requests to stay within API limits.
        """
        client = self._get_client()
        # OpenAI allows up to 2048 inputs per request
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Clean inputs — replace newlines which degrade quality
            batch = [text.replace("\n", " ") for text in batch]

            response = client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def embed_single(self, text: str) -> List[float]:
        return self.embed([text])[0]

    @property
    def embedding_dim(self) -> int:
        dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dims.get(self.model_name, 1536)


@lru_cache(maxsize=1)
def get_embedding_provider() -> Union[SentenceTransformerEmbeddings, OpenAIEmbeddings]:
    """
    Factory function that returns the configured embedding provider.
    Result is cached so the model is loaded only once.
    """
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set for OpenAI embeddings")
        logger.info("Using OpenAI embeddings provider")
        return OpenAIEmbeddings()
    else:
        logger.info("Using SentenceTransformers embeddings provider")
        return SentenceTransformerEmbeddings()
