"""AI Provider Registry.

Resolves configured LLM and embedding providers based on environment settings.
Supports both real AI providers (Gemini, SentenceTransformers) and offline
deterministic fallback mocks.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.ai.exceptions import AIConfigurationError
from app.ai.interfaces import EmbeddingProvider, LLMProvider
from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider
from app.core.config import get_settings


class AIProviderStatus(BaseModel):
    """Runtime status of AI providers."""
    text_provider: str
    embedding_provider: str
    text_provider_type: Literal["real", "deterministic_mock"]
    embedding_provider_type: Literal["real", "deterministic_mock"]
    mode: Literal["REAL_AI", "DETERMINISTIC_DEMO", "HYBRID"]
    implemented: bool = True


def get_llm_provider() -> LLMProvider:
    """Return configured LLM provider or deterministic mock fallback."""
    settings = get_settings()
    provider_key = (settings.ai_text_provider or "").strip().lower()

    if provider_key in {"", "stub", "deterministic_mock"}:
        return DeterministicMockProvider()

    if provider_key == "gemini":
        from app.ai.gemini_provider import GeminiLLMProvider

        return GeminiLLMProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.ai_text_model,
        )

    raise AIConfigurationError(
        f"Unknown or unsupported AI text provider '{settings.ai_text_provider}'. "
        "Supported providers are 'gemini' or 'deterministic_mock' (or 'stub')."
    )


def get_embedding_provider() -> EmbeddingProvider:
    """Return configured semantic embedding provider or deterministic mock fallback."""
    settings = get_settings()
    provider_key = (settings.ai_embedding_provider or "").strip().lower()

    if provider_key in {"", "stub", "deterministic_mock"}:
        return DeterministicEmbeddingProvider()

    if provider_key in {"sentence_transformers", "sentencetransformers"}:
        from app.ai.sentence_transformer_provider import SentenceTransformersEmbeddingProvider

        return SentenceTransformersEmbeddingProvider(
            model_name=settings.ai_embedding_model,
        )

    raise AIConfigurationError(
        f"Unknown or unsupported AI embedding provider '{settings.ai_embedding_provider}'. "
        "Supported providers are 'sentence_transformers' or 'deterministic_mock' (or 'stub')."
    )


def get_ai_status() -> AIProviderStatus:
    """Return current configuration status of AI providers."""
    settings = get_settings()
    t_key = (settings.ai_text_provider or "deterministic_mock").strip().lower()
    e_key = (settings.ai_embedding_provider or "deterministic_mock").strip().lower()

    t_type = "real" if t_key == "gemini" else "deterministic_mock"
    e_type = "real" if e_key in {"sentence_transformers", "sentencetransformers"} else "deterministic_mock"

    if t_type == "real" and e_type == "real":
        mode = "REAL_AI"
    elif t_type == "deterministic_mock" and e_type == "deterministic_mock":
        mode = "DETERMINISTIC_DEMO"
    else:
        mode = "HYBRID"

    return AIProviderStatus(
        text_provider=t_key,
        embedding_provider=e_key,
        text_provider_type=t_type,
        embedding_provider_type=e_type,
        mode=mode,
        implemented=True,
    )
