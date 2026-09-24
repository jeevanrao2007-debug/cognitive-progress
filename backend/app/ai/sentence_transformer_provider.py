"""Sentence Transformers semantic embedding provider.

Loads a local SentenceTransformer model lazily to keep startup times fast and
allow fully offline semantic vector generation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.interfaces import EmbeddingProvider
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_LOADED_MODELS: dict[str, Any] = {}


class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Generates real semantic vector embeddings using local sentence-transformers."""

    provider_name: str = "sentence_transformers"

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.ai_embedding_model or "all-MiniLM-L6-v2"
        self._model: Any | None = None

    @property
    def dimensions(self) -> int:
        """Embedding vector dimension (384 for all-MiniLM-L6-v2)."""
        return 384

    @property
    def model(self) -> Any:
        """Lazy-load the SentenceTransformer model on first invocation."""
        if self._model is not None:
            return self._model
        if self.model_name in _LOADED_MODELS:
            self._model = _LOADED_MODELS[self.model_name]
            return self._model

        logger.info("Initializing SentenceTransformer model: %s", self.model_name)
        try:
            from sentence_transformers import SentenceTransformer

            loaded = SentenceTransformer(self.model_name)
            _LOADED_MODELS[self.model_name] = loaded
            self._model = loaded
        except ImportError as err:
            raise AIConfigurationError(
                "sentence-transformers is not installed. Install with `pip install sentence-transformers`."
            ) from err
        except Exception as err:
            raise AIProviderError(
                f"Failed to load SentenceTransformer model '{self.model_name}': {err}"
            ) from err
        return self._model

    def embed(self, text: str) -> list[float]:
        """Embed text into a normalized dense vector."""
        if not text:
            text = ""
        try:
            vector = self.model.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return [float(x) for x in vector.tolist()]
        except Exception as err:
            raise AIProviderError(
                f"SentenceTransformers embedding generation failed: {err}"
            ) from err

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed multiple texts into normalized dense vectors."""
        if not texts:
            return []
        try:
            vectors = self.model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return [[float(x) for x in vec.tolist()] for vec in vectors]
        except Exception as err:
            raise AIProviderError(
                f"SentenceTransformers batch embedding generation failed: {err}"
            ) from err

