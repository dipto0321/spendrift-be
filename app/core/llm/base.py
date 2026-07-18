"""LLM client protocol and errors.

Mirrors the storage pattern: a hardcoded provider implementation lives
behind a small Protocol so tests (and future providers) can swap it via
the `get_llm` dependency without touching business code.
"""

from typing import Any, Protocol


class LLMError(Exception):
    """The provider call failed (network, quota, malformed output)."""


class LLMNotConfiguredError(LLMError):
    """No API key configured — AI features are unavailable."""


class LLMClient(Protocol):
    """A model that can answer a prompt with schema-constrained JSON."""

    def generate_structured(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        """Return the parsed JSON payload matching `response_schema`.

        Raises LLMNotConfiguredError when no credentials are configured
        and LLMError for any provider-side failure.
        """
        ...
