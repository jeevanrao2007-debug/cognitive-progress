from typing import Protocol


class LLMProvider(Protocol):
    """Provider boundary. Implementations return JSON, never domain objects."""

    provider_name: str
    model_name: str | None

    def extract_progress(self, prompt: str) -> str:
        """Return JSON that conforms to the extraction batch schema."""

    def normalize_activity(self, prompt: str) -> str:
        """Return JSON that conforms to the normalization schema."""

    def explain_reconciliation(self, prompt: str) -> str:
        """Reserved for a later reconciliation phase."""


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for text."""
