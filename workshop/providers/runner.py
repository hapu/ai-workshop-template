"""Safe execution wrapper: policy check and quota reservation before provider I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .base import ChatProvider, Message, ProviderResponse
from .policy import FreeTierGate, ProviderRegistry
from .usage_ledger import UsageLedger, UsageReservation


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    response: ProviderResponse
    reservation: UsageReservation


def execute_with_free_tier_gate(
    provider_adapter: ChatProvider,
    *,
    registry: ProviderRegistry,
    ledger: UsageLedger,
    model: str,
    messages: Sequence[Message],
    input_tokens: int,
    max_output_tokens: int,
    region: str,
    neurons: int = 0,
    account_scope: str,
    request_id: str | None = None,
) -> ProviderCallResult:
    """Validate, reserve local quota, then call the provider adapter.

    input_tokens must conservatively include all system messages and context.
    Maximum output tokens and any metered Neurons are reserved before network I/O.
    Reservations are not refunded after ambiguous transport failures.
    """
    provider_id = provider_adapter.provider_id.strip().lower()
    approval = FreeTierGate(registry).authorize(
        provider=provider_id, model=model, input_tokens=input_tokens,
        output_tokens=max_output_tokens, region=region,
    )
    policy = registry.require(provider_id, model)
    reservation = ledger.reserve(
        policy, account_scope=account_scope,
        input_tokens=approval.input_tokens, output_tokens=approval.output_tokens,
        neurons=neurons, request_id=request_id,
    )
    response = provider_adapter.complete(
        model=model, messages=messages, max_output_tokens=max_output_tokens,
    )
    if response.provider.strip().lower() != provider_id or response.model != model:
        raise RuntimeError("Provider response identity does not match the authorized request")
    return ProviderCallResult(response, reservation)
