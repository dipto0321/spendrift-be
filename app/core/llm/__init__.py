"""LLM factory — returns the configured client as a FastAPI dependency."""

from functools import lru_cache

from app.core.llm.gemini import GeminiClient


@lru_cache(maxsize=1)
def _build_llm() -> GeminiClient:
    return GeminiClient()


def get_llm() -> GeminiClient:
    """FastAPI dependency that returns the singleton LLM client."""
    return _build_llm()
