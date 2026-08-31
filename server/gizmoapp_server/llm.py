"""Small fail-closed helper for the AI100 course model gateway."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency missing until installation
    OpenAI = None

DEFAULT_MAX_TOKENS = 1000
MAX_ALLOWED_TOKENS = 4096
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 55.0
ALLOWED_ROLES = frozenset({"system", "user", "assistant"})


class CourseLLMError(RuntimeError):
    """A safe, user-displayable course-model failure."""


_client = None
_client_signature: tuple[str, str, float] | None = None


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CourseLLMError(
            f"{name} is not set. The AI100 platform supplies all course-model settings; "
            "restart the app or server session and try again."
        )
    return value


def _timeout_seconds() -> float:
    raw_value = os.environ.get("GIZMO_LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise CourseLLMError("GIZMO_LLM_TIMEOUT_SECONDS must be numeric.") from exc
    if value <= 0 or value > MAX_TIMEOUT_SECONDS:
        raise CourseLLMError(
            f"GIZMO_LLM_TIMEOUT_SECONDS must be greater than zero and at most {MAX_TIMEOUT_SECONDS:g}."
        )
    return value


def _get_client():
    global _client, _client_signature
    if OpenAI is None:
        raise CourseLLMError(
            "The 'openai' package is not installed. Run: pip install -r server/requirements.txt"
        )

    api_key = _required_environment("GIZMO_LLM_API_KEY")
    base_url = _required_environment("GIZMO_LLM_BASE_URL")
    timeout = _timeout_seconds()
    signature = (api_key, base_url, timeout)
    if _client is None or _client_signature != signature:
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=1,
        )
        _client_signature = signature
    return _client


def model_name() -> str:
    """Return the model id explicitly assigned by the course platform."""
    return _required_environment("GIZMO_LLM_MODEL")


def _validate_max_tokens(max_tokens: int) -> int:
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise CourseLLMError("max_tokens must be an integer.")
    if max_tokens < 1 or max_tokens > MAX_ALLOWED_TOKENS:
        raise CourseLLMError(f"max_tokens must be between 1 and {MAX_ALLOWED_TOKENS}.")
    return max_tokens


def _validate_messages(messages: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(messages, (str, bytes)) or not isinstance(messages, Sequence) or not messages:
        raise CourseLLMError("messages must be a non-empty sequence of message objects.")

    validated: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise CourseLLMError("each message must be an object with role and content strings.")
        role = message.get("role")
        content = message.get("content")
        if role not in ALLOWED_ROLES or not isinstance(content, str) or not content.strip():
            raise CourseLLMError(
                "each message must have a system, user, or assistant role and non-empty text content."
            )
        validated.append({"role": role, "content": content})
    return validated


def chat(messages: Sequence[dict[str, Any]], max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Send validated messages and return the assistant's text response."""
    validated_messages = _validate_messages(messages)
    validated_max_tokens = _validate_max_tokens(max_tokens)
    try:
        response = _get_client().chat.completions.create(
            model=model_name(),
            messages=validated_messages,
            max_tokens=validated_max_tokens,
        )
    except CourseLLMError:
        raise
    except Exception as exc:
        raise CourseLLMError(
            "The course model is temporarily unavailable. Please wait a moment and try again."
        ) from exc

    if not response.choices:
        raise CourseLLMError("The course model returned no response. Please try again.")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise CourseLLMError("The course model returned an empty response. Please try again.")
    return content


def ask(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Send one user prompt to the course model."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise CourseLLMError("prompt must be non-empty text.")
    return chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
