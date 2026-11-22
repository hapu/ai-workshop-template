"""OpenRouter Chat Completions adapter using only the Python standard library."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Sequence

from .base import Message, ProviderResponse

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_ALLOWED_ROLES = frozenset({"system", "user", "assistant"})


class ProviderTransportError(Exception):
    """Safe-to-display provider transport or response error."""


class OpenRouterAdapter:
    """Minimal non-streaming adapter. Always disables provider-level fallbacks."""

    provider_id = "openrouter"

    def __init__(self, api_key: str, *, timeout_seconds: float = 30.0) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("OpenRouter API key is required")
        if timeout_seconds <= 0:
            raise ValueError("Timeout must be greater than zero")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        max_output_tokens: int,
    ) -> ProviderResponse:
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise ValueError("Model ID must be a non-empty string")
        if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
            raise ValueError("Maximum output tokens must be a positive integer")
        if not messages:
            raise ValueError("At least one message is required")

        serialized_messages: list[dict[str, str]] = []
        for message in messages:
            if message.role not in _ALLOWED_ROLES:
                raise ValueError(f"Unsupported message role: {message.role}")
            if not isinstance(message.content, str):
                raise ValueError("Message content must be text")
            serialized_messages.append({"role": message.role, "content": message.content})

        payload = {
            "model": model.strip(),
            "messages": serialized_messages,
            "max_tokens": max_output_tokens,
            "stream": False,
            "provider": {"allow_fallbacks": False},
        }
        request = Request(
            _ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                request_id = response.headers.get("X-Generation-Id") or response.headers.get("X-Request-Id")
        except HTTPError as exc:
            raise ProviderTransportError(
                f"OpenRouter returned HTTP {exc.code}; request was not retried"
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = "network error" if isinstance(exc, URLError) else "connection or timeout error"
            raise ProviderTransportError(f"OpenRouter {reason}; request was not retried") from None

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ProviderTransportError("OpenRouter response exceeded the 2 MiB safety limit")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ProviderTransportError("OpenRouter returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ProviderTransportError("OpenRouter response must be a JSON object")
        returned_model = result.get("model")
        choices = result.get("choices")
        if returned_model != model or not isinstance(choices, list) or not choices:
            raise ProviderTransportError("OpenRouter response model or choices did not match the request")
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise ProviderTransportError("OpenRouter response did not contain a text completion")

        usage = result.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        input_tokens = _optional_count(usage.get("prompt_tokens"))
        output_tokens = _optional_count(usage.get("completion_tokens"))
        response_id = result.get("id")
        if not isinstance(request_id, str) or not request_id.strip():
            request_id = response_id if isinstance(response_id, str) else None

        return ProviderResponse(
            provider=self.provider_id,
            model=model,
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=request_id,
        )


def _optional_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
