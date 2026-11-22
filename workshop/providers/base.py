"""Small provider-agnostic interfaces for future inference adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    provider: str
    model: str
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None


class ChatProvider(Protocol):
    """Contract implemented by optional providers; implementations must not bypass the gate."""

    @property
    def provider_id(self) -> str: ...

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        max_output_tokens: int,
    ) -> ProviderResponse: ...
