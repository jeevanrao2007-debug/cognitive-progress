"""Official Google Gemini Python SDK provider implementation for LLM operations."""

from __future__ import annotations

import json
import logging
import re

from google import genai
from google.genai import types

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.interfaces import LLMProvider
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def clean_json_response(raw_text: str) -> str:
    """Strip markdown code fence wrappers if present and return clean JSON string."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    return text


class GeminiLLMProvider(LLMProvider):
    """Official Google Gemini Python SDK provider implementation for LLM operations."""

    provider_name: str = "gemini"

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        resolved_key = api_key or settings.gemini_api_key
        if not resolved_key or not resolved_key.strip():
            raise AIConfigurationError(
                "GEMINI_API_KEY is required when AI_TEXT_PROVIDER is set to 'gemini'. "
                "Please configure GEMINI_API_KEY in your environment or .env file, "
                "or switch to AI_TEXT_PROVIDER=deterministic_mock for offline demo mode."
            )
        self.api_key = resolved_key.strip()
        self.model_name = model_name or settings.ai_text_model or "gemini-2.5-flash"
        try:
            self._client = genai.Client(api_key=self.api_key)
        except Exception as err:
            raise AIConfigurationError(f"Failed to initialize Gemini client: {err}") from err

    def extract_progress(self, prompt: str) -> str:
        """Call Gemini to extract structured observation records conforming to ExtractionBatch schema."""
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            cleaned = clean_json_response(response.text or "{}")
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError as err:
            raise AIProviderError(f"Gemini returned invalid JSON: {err}") from err
        except Exception as err:
            raise AIProviderError(f"Gemini LLM call failed: {err}") from err

    def normalize_activity(self, prompt: str) -> str:
        """Call Gemini to produce canonical activity, discipline, and location fields."""
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            cleaned = clean_json_response(response.text or "{}")
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError as err:
            raise AIProviderError(f"Gemini returned invalid JSON: {err}") from err
        except Exception as err:
            raise AIProviderError(f"Gemini LLM call failed: {err}") from err

    def explain_reconciliation(self, prompt: str) -> str:
        """Call Gemini to generate a traceable explanation and recommendation for reconciliation decisions."""
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            cleaned = clean_json_response(response.text or "{}")
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError as err:
            raise AIProviderError(f"Gemini returned invalid JSON: {err}") from err
        except Exception as err:
            raise AIProviderError(f"Gemini LLM call failed: {err}") from err

