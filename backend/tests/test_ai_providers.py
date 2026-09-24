"""Unit and integration tests for AI providers, configuration, and registry."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.gemini_provider import GeminiLLMProvider, clean_json_response
from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider
from app.ai.registry import get_ai_status, get_embedding_provider, get_llm_provider
from app.ai.sentence_transformer_provider import SentenceTransformersEmbeddingProvider
from app.core.config import Settings
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------
# Clean JSON response helper tests
# ---------------------------------------------------------

def test_clean_json_response_with_markdown_fences() -> None:
    raw = "```json\n{\"observation_id\": \"123\"}\n```"
    assert clean_json_response(raw) == '{"observation_id": "123"}'


def test_clean_json_response_plain() -> None:
    raw = '{"status": "ok"}'
    assert clean_json_response(raw) == '{"status": "ok"}'


# ---------------------------------------------------------
# Gemini Provider Tests
# ---------------------------------------------------------

def test_gemini_provider_missing_key_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with patch("app.ai.gemini_provider.get_settings") as mock_settings:
        mock_settings.return_value = Settings(gemini_api_key=None)
        with pytest.raises(AIConfigurationError) as exc_info:
            GeminiLLMProvider(api_key=None)
        assert "GEMINI_API_KEY is required" in str(exc_info.value)


@patch("app.ai.gemini_provider.genai.Client")
def test_gemini_extract_progress_success(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"observations": [{"id": "obs-1"}]}'
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="test-dummy-key-12345", model_name="gemini-2.5-flash")
    result = provider.extract_progress("Extract this document")

    assert '"obs-1"' in result
    mock_client.models.generate_content.assert_called_once()


@patch("app.ai.gemini_provider.genai.Client")
def test_gemini_normalize_activity_success(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '```json\n{"canonical_activity": "Concrete Pouring"}\n```'
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="test-dummy-key-12345")
    result = provider.normalize_activity("Normalize this activity")

    assert "Concrete Pouring" in result


@patch("app.ai.gemini_provider.genai.Client")
def test_gemini_explain_reconciliation_success(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"explanation": "Reconciliation verified against schedule."}'
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="test-dummy-key-12345")
    result = provider.explain_reconciliation("Explain reconciliation")

    assert "Reconciliation verified" in result


@patch("app.ai.gemini_provider.genai.Client")
def test_gemini_provider_api_failure_raises_provider_error(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("API connection timeout")

    provider = GeminiLLMProvider(api_key="test-dummy-key-12345")
    with pytest.raises(AIProviderError) as exc_info:
        provider.extract_progress("Extract")
    assert "Gemini LLM call failed" in str(exc_info.value)


# ---------------------------------------------------------
# SentenceTransformers Provider Tests
# ---------------------------------------------------------

def test_sentence_transformers_lazy_loading() -> None:
    """Ensure the underlying model is NOT loaded when the provider is instantiated."""
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    assert provider._model is None


def test_sentence_transformers_embed_with_mock() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    mock_model = MagicMock()
    mock_vec = MagicMock()
    mock_vec.tolist.return_value = [0.1, 0.2, 0.3, 0.4]
    mock_model.encode.return_value = mock_vec
    provider._model = mock_model

    result = provider.embed("Sample construction progress text")
    assert result == [0.1, 0.2, 0.3, 0.4]
    mock_model.encode.assert_called_once_with(
        "Sample construction progress text",
        convert_to_numpy=True,
        normalize_embeddings=True,
    )


# ---------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------

def test_registry_returns_deterministic_mock_by_default() -> None:
    with patch("app.ai.registry.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            ai_text_provider="deterministic_mock",
            ai_embedding_provider="deterministic_mock",
        )
        llm = get_llm_provider()
        emb = get_embedding_provider()
        status = get_ai_status()

        assert isinstance(llm, DeterministicMockProvider)
        assert isinstance(emb, DeterministicEmbeddingProvider)
        assert status.mode == "DETERMINISTIC_DEMO"
        assert status.text_provider_type == "deterministic_mock"


@patch("app.ai.gemini_provider.genai.Client")
def test_registry_returns_gemini_and_sentence_transformers(mock_client: MagicMock) -> None:
    with patch("app.ai.registry.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            ai_text_provider="gemini",
            ai_embedding_provider="sentence_transformers",
            gemini_api_key="test-api-key",
        )
        llm = get_llm_provider()
        emb = get_embedding_provider()
        status = get_ai_status()

        assert isinstance(llm, GeminiLLMProvider)
        assert isinstance(emb, SentenceTransformersEmbeddingProvider)
        assert status.mode == "REAL_AI"
        assert status.text_provider_type == "real"
        assert status.embedding_provider_type == "real"


def test_registry_unknown_text_provider_raises_config_error() -> None:
    with patch("app.ai.registry.get_settings") as mock_settings:
        mock_settings.return_value = Settings(ai_text_provider="nonexistent_provider")
        with pytest.raises(AIConfigurationError) as exc_info:
            get_llm_provider()
        assert "Unknown or unsupported AI text provider" in str(exc_info.value)


# ---------------------------------------------------------
# Health Route Integration Test
# ---------------------------------------------------------

def test_health_route_includes_ai_status() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ai_status" in data
    assert data["ai_status"]["implemented"] is True
    assert data["ai_status"]["mode"] in {"REAL_AI", "DETERMINISTIC_DEMO", "HYBRID"}
