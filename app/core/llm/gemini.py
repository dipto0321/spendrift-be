"""Gemini implementation of the LLM client.

Calls the Generative Language REST API directly with httpx — no SDK
dependency. Structured output is enforced through `responseMimeType`
+ `responseSchema` in the generation config, so the model replies with
JSON that parses straight into Python values.
"""

import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.llm.base import LLMError, LLMNotConfiguredError

logger = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient:
    """Thin, synchronous Gemini wrapper (routes run in the threadpool)."""

    def generate_structured(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        if not settings.gemini_api_key:
            raise LLMNotConfiguredError("GEMINI_API_KEY is not set")

        url = f"{_API_BASE}/models/{settings.gemini_model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
                # Parsing wants determinism, not creativity.
                "temperature": 0,
            },
        }

        try:
            response = httpx.post(
                url,
                json=body,
                headers={"x-goog-api-key": settings.gemini_api_key},
                timeout=settings.gemini_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "gemini call failed: %s %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise LLMError(f"Gemini returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("gemini call failed: %s", exc)
            raise LLMError("Gemini request failed") from exc

        try:
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("gemini returned an unexpected payload: %s", exc)
            raise LLMError("Gemini returned an unexpected payload") from exc
