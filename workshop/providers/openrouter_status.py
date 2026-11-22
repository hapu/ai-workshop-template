"""Read-only OpenRouter current-key status retrieval.

This module performs one authenticated GET only. It never sends inference,
never retries, never follows redirects, and never exposes response bodies in
transport errors.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any

_ENDPOINT = "https://openrouter.ai/api/v1/key"
_MAX_RESPONSE_BYTES = 1024 * 1024


class OpenRouterStatusError(Exception):
    """Safe-to-display error while retrieving OpenRouter key status."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        return None


@dataclass(frozen=True, slots=True)
class OpenRouterKeyStatus:
    daily_requests_used: int
    daily_requests_limit: int
    daily_requests_remaining: int
    key_credit_remaining: float | None
    effective_budget_remaining: float | None
    budget_count: int


def fetch_openrouter_key_status(api_key: str, *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Fetch the authenticated current-key endpoint once, without redirects."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise OpenRouterStatusError("OPENROUTER_API_KEY is not set")
    if timeout_seconds <= 0:
        raise ValueError("Timeout must be greater than zero")
    request = Request(
        _ENDPOINT,
        headers={"Authorization": f"Bearer {api_key.strip()}", "Accept": "application/json"},
        method="GET",
    )
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise OpenRouterStatusError(
            f"OpenRouter key-status endpoint returned HTTP {exc.code}; no retry was attempted"
        ) from None
    except (URLError, TimeoutError, OSError):
        raise OpenRouterStatusError(
            "OpenRouter key-status request failed due to a network or timeout error; no retry was attempted"
        ) from None
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise OpenRouterStatusError("OpenRouter key-status response exceeded the 1 MiB safety limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise OpenRouterStatusError("OpenRouter key-status endpoint returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise OpenRouterStatusError("OpenRouter key-status response must be a JSON object")
    return payload


def parse_openrouter_key_status(payload: dict[str, Any]) -> OpenRouterKeyStatus:
    """Validate and return only non-secret quota/budget metadata."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise OpenRouterStatusError("OpenRouter key-status response is missing its data object")
    data = payload["data"]
    daily = data.get("free_model_daily_requests")
    if not isinstance(daily, dict):
        raise OpenRouterStatusError("OpenRouter response is missing free_model_daily_requests")

    def count(name: str) -> int:
        value = daily.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise OpenRouterStatusError(f"free_model_daily_requests.{name} must be a non-negative integer")
        return value

    used, limit, remaining = count("used"), count("limit"), count("remaining")
    if limit <= 0 or used + remaining != limit:
        raise OpenRouterStatusError("OpenRouter daily request counters are inconsistent")

    def amount(value: Any, field: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise OpenRouterStatusError(f"{field} must be a finite number or null")
        return float(value)

    if "limit_remaining" not in data:
        raise OpenRouterStatusError("OpenRouter response is missing limit_remaining")
    credit_remaining = amount(data["limit_remaining"], "limit_remaining")
    budgets = data.get("budgets")
    if not isinstance(budgets, list):
        raise OpenRouterStatusError("OpenRouter response budgets must be an array")
    for index, budget in enumerate(budgets):
        if not isinstance(budget, dict) or not isinstance(budget.get("scope"), str):
            raise OpenRouterStatusError(f"OpenRouter budget {index} is malformed")
        for field in ("limit_usd", "spend_usd", "remaining_usd"):
            if field not in budget:
                raise OpenRouterStatusError(f"OpenRouter budget {index} is missing {field}")
            amount(budget[field], f"budgets[{index}].{field}")
    effective = data.get("effective_budget")
    if effective is not None:
        if not isinstance(effective, dict) or not isinstance(effective.get("scope"), str):
            raise OpenRouterStatusError("OpenRouter effective_budget is malformed")
        if "remaining_usd" not in effective:
            raise OpenRouterStatusError("OpenRouter effective_budget is missing remaining_usd")
        effective_remaining = amount(effective["remaining_usd"], "effective_budget.remaining_usd")
    else:
        effective_remaining = None

    return OpenRouterKeyStatus(
        daily_requests_used=used,
        daily_requests_limit=limit,
        daily_requests_remaining=remaining,
        key_credit_remaining=credit_remaining,
        effective_budget_remaining=effective_remaining,
        budget_count=len(budgets),
    )
