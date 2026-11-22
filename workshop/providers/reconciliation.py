"""Validated external quota snapshots for fail-closed provider reconciliation."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .policy import ModelPolicy, ProviderCatalogError

_SOURCE_TYPES = frozenset({"api", "dashboard", "manual", "response_headers"})
_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")


class SnapshotError(ProviderCatalogError):
    """Raised when an external quota snapshot is missing, stale, or inconsistent."""


def _utc_timestamp(value: Any, field_name: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise SnapshotError(f"{field_name} must be a UTC ISO-8601 timestamp")
    clean = value.strip()
    try:
        parsed = datetime.fromisoformat(clean[:-1] + "+00:00" if clean.endswith("Z") else clean)
    except ValueError as exc:
        raise SnapshotError(f"{field_name} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise SnapshotError(f"{field_name} must include a UTC timezone")
    return parsed.timestamp()


def _utc_text(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def openrouter_key_response_to_snapshot(
    payload: dict[str, Any],
    policy: ModelPolicy,
    *,
    account_scope: str,
    captured_at: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Convert the safe GET /api/v1/key response subset into a canonical snapshot.

    OpenRouter reports the free-model daily request counter and UTC-day ceiling
    here, but not all model/provider RPM or token limits. Other policy quotas
    therefore still need their own dashboard/header snapshots.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise SnapshotError("OpenRouter key response must contain a data object")
    daily = payload["data"].get("free_model_daily_requests")
    if not isinstance(daily, dict):
        raise SnapshotError("OpenRouter response is missing data.free_model_daily_requests")
    used = daily.get("used")
    limit = daily.get("limit")
    remaining = daily.get("remaining")
    for name, value in (("used", used), ("limit", limit), ("remaining", remaining)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SnapshotError(f"OpenRouter free_model_daily_requests.{name} must be a non-negative integer")
    if limit <= 0 or used + remaining != limit:
        raise SnapshotError("OpenRouter daily used + remaining must equal a positive limit")
    matching = [
        quota for quota in policy.quotas
        if quota.metric == "requests" and quota.window_seconds == 86400 and quota.scope == "account"
    ]
    if len(matching) != 1:
        raise SnapshotError("Selected model policy must define exactly one account-scoped 86400-second requests quota")
    if limit != matching[0].limit:
        raise SnapshotError(
            f"OpenRouter daily limit {limit} does not match the policy limit {matching[0].limit}"
        )
    captured = _utc_timestamp(captured_at, "captured_at")
    captured_dt = datetime.fromtimestamp(captured, timezone.utc)
    next_midnight = datetime(
        captured_dt.year, captured_dt.month, captured_dt.day, tzinfo=timezone.utc
    ).timestamp() + 86400
    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "provider": policy.provider,
        "model": policy.model,
        "account_scope": account_scope,
        "source_type": "api",
        "source_url": "https://openrouter.ai/api/v1/key",
        "captured_at": _utc_text(captured),
        "quotas": [{
            "metric": "requests",
            "window_seconds": 86400,
            "scope": "account",
            "used": used,
            "limit": limit,
            "reset_at": _utc_text(next_midnight),
        }],
    }


@dataclass(frozen=True, slots=True)
class SnapshotQuota:
    metric: str
    window_seconds: int
    scope: str
    used: int
    limit: int
    reset_at: float


@dataclass(frozen=True, slots=True)
class ExternalQuotaSnapshot:
    snapshot_id: str
    provider: str
    model: str
    account_scope: str
    source_type: str
    source_url: str
    captured_at: float
    quotas: tuple[SnapshotQuota, ...]

    @classmethod
    def from_dict(
        cls, raw: dict[str, Any], policy: ModelPolicy, *, now: float | None = None
    ) -> "ExternalQuotaSnapshot":
        if not isinstance(raw, dict):
            raise SnapshotError("Quota snapshot must be a JSON object")
        forbidden = {"key", "token", "api_key", "apikey", "authorization", "access_token", "refresh_token", "client_secret", "secret", "password"}
        def reject_secrets(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if isinstance(key, str) and key.casefold().replace("-", "_") in forbidden:
                        raise SnapshotError("Snapshot must not contain credentials or secret fields")
                    reject_secrets(child)
            elif isinstance(value, list):
                for child in value:
                    reject_secrets(child)
        reject_secrets(raw)

        if isinstance(raw.get("schema_version"), bool) or raw.get("schema_version") != 1:
            raise SnapshotError("Snapshot schema_version must be integer 1")
        snapshot_id = raw.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise SnapshotError("snapshot_id must be 1-120 letters, digits, dots, underscores, colons, or hyphens")
        provider = raw.get("provider")
        model = raw.get("model")
        account_scope = raw.get("account_scope")
        source_type = raw.get("source_type")
        source_url = raw.get("source_url")
        for field_name, value in (
            ("provider", provider), ("model", model), ("account_scope", account_scope),
            ("source_type", source_type), ("source_url", source_url),
        ):
            if not isinstance(value, str) or not value.strip():
                raise SnapshotError(f"{field_name} must be a non-empty string")
        if provider.strip().lower() != policy.provider or model.strip() != policy.model:
            raise SnapshotError("Snapshot provider/model do not match the selected catalog policy")
        if not account_scope.strip() or len(account_scope.strip()) > 120:
            raise SnapshotError("account_scope must be a non-empty local alias up to 120 characters")
        if source_type not in _SOURCE_TYPES:
            raise SnapshotError("source_type must be api, dashboard, manual, or response_headers")
        parsed_url = urlparse(source_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username or parsed_url.password or parsed_url.query:
            raise SnapshotError("source_url must be a credential-free HTTPS URL")

        captured_at = _utc_timestamp(raw.get("captured_at"), "captured_at")
        current_time = datetime.now(timezone.utc).timestamp() if now is None else float(now)
        if captured_at > current_time:
            raise SnapshotError("captured_at cannot be in the future")

        raw_quotas = raw.get("quotas")
        if not isinstance(raw_quotas, list) or not raw_quotas:
            raise SnapshotError("Snapshot must contain at least one quota entry")
        parsed_quotas: list[SnapshotQuota] = []
        seen: set[tuple[str, int, str]] = set()
        for item in raw_quotas:
            if not isinstance(item, dict):
                raise SnapshotError("Every snapshot quota entry must be an object")
            required = {"metric", "window_seconds", "scope", "used", "limit", "reset_at"}
            missing = required.difference(item)
            if missing:
                raise SnapshotError("Quota snapshot entry is missing: " + ", ".join(sorted(missing)))
            metric, window, scope = item["metric"], item["window_seconds"], item["scope"]
            if not isinstance(metric, str) or not isinstance(scope, str):
                raise SnapshotError("Snapshot metric and scope must be strings")
            if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
                raise SnapshotError("Snapshot window_seconds must be a positive integer")
            matching = [
                quota for quota in policy.quotas
                if quota.metric == metric and quota.window_seconds == window and quota.scope == scope
            ]
            if len(matching) != 1:
                raise SnapshotError(f"Snapshot quota {metric}/{window}s/{scope} is not in the selected policy")
            policy_quota = matching[0]
            if "limit" not in item or isinstance(item["limit"], bool) or not isinstance(item["limit"], int):
                raise SnapshotError("Snapshot quota limit must be an integer")
            if item["limit"] != policy_quota.limit:
                raise SnapshotError(
                    f"Snapshot limit for {metric}/{window}s does not match the verified policy "
                    f"({item['limit']} != {policy_quota.limit})"
                )
            used = item["used"]
            if isinstance(used, bool) or not isinstance(used, int) or used < 0:
                raise SnapshotError("Snapshot used value must be a non-negative integer")
            key = (metric, window, scope)
            if key in seen:
                raise SnapshotError(f"Duplicate snapshot quota entry: {key}")
            seen.add(key)
            reset_at = _utc_timestamp(item["reset_at"], "reset_at")
            if reset_at <= captured_at or reset_at > captured_at + window:
                raise SnapshotError("reset_at must be after capture and within the quota window")
            parsed_quotas.append(
                SnapshotQuota(metric, window, scope, used, item["limit"], reset_at)
            )

        return cls(
            snapshot_id=snapshot_id,
            provider=policy.provider,
            model=policy.model,
            account_scope=account_scope.strip(),
            source_type=source_type,
            source_url=source_url.strip(),
            captured_at=captured_at,
            quotas=tuple(parsed_quotas),
        )

    def captured_at_text(self) -> str:
        return _utc_text(self.captured_at)


_GROQ_SOURCE_URL = "https://console.groq.com/docs/rate-limits"
_GROQ_DURATION_TOKEN = re.compile(r"(\d+(?:\.\d+)?)([dhms])")
_GROQ_HEADER_NAMES = frozenset({
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
})
_GROQ_SECRET_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "x-auth-token",
})


def _duration_seconds(value: Any, field_name: str) -> int:
    """Parse a provider duration such as 2m59.56s, rounding up to a safe second."""
    if not isinstance(value, str) or not value.strip():
        raise SnapshotError(f"{field_name} must be a duration such as 7.66s")
    clean = value.strip()
    units = {"d": Decimal(86400), "h": Decimal(3600), "m": Decimal(60), "s": Decimal(1)}
    order = {"d": 0, "h": 1, "m": 2, "s": 3}
    position = 0
    previous_order = -1
    total = Decimal(0)
    while position < len(clean):
        match = _GROQ_DURATION_TOKEN.match(clean, position)
        if match is None:
            raise SnapshotError(f"{field_name} is not a supported duration")
        amount_text, unit = match.groups()
        if order[unit] <= previous_order:
            raise SnapshotError(f"{field_name} units must be unique and ordered from largest to smallest")
        try:
            amount = Decimal(amount_text)
        except InvalidOperation as exc:
            raise SnapshotError(f"{field_name} is not a valid duration") from exc
        total += amount * units[unit]
        previous_order = order[unit]
        position = match.end()
    if total <= 0:
        raise SnapshotError(f"{field_name} must be greater than zero")
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def _header_integer(headers: dict[str, str], name: str) -> int:
    value = headers[name]
    if not re.fullmatch(r"\d+", value.strip()):
        raise SnapshotError(f"Groq header {name} must be a non-negative integer")
    return int(value.strip())


def groq_response_headers_to_snapshot(
    headers: dict[str, Any],
    policy: ModelPolicy,
    *,
    account_scope: str,
    captured_at: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Convert saved Groq response rate-limit headers into a canonical snapshot.

    The documented headers expose RPD (requests/day) and combined TPM
    (input + output tokens/minute). They do not expose every dashboard limit.
    """
    if policy.provider != "groq":
        raise SnapshotError("Groq response headers can only be imported for a Groq policy")
    if not isinstance(headers, dict):
        raise SnapshotError("Groq headers file must be a JSON object of header names and values")

    normalized: dict[str, str] = {}
    seen: set[str] = set()
    for raw_name, raw_value in headers.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise SnapshotError("Every Groq header name must be a non-empty string")
        name = raw_name.strip().casefold()
        if name in _GROQ_SECRET_HEADERS:
            raise SnapshotError("Do not import credentials, cookies, or authorization headers")
        if name in seen:
            raise SnapshotError(f"Duplicate Groq header name: {name}")
        seen.add(name)
        if name in _GROQ_HEADER_NAMES:
            if not isinstance(raw_value, str) or not raw_value.strip():
                raise SnapshotError(f"Groq header {name} must be a non-empty string")
            normalized[name] = raw_value.strip()

    captured = _utc_timestamp(captured_at, "captured_at")
    mapping = (
        ("requests", 86400, "requests"),
        ("tokens", 60, "tokens"),
    )
    quotas: list[dict[str, Any]] = []
    for metric, window_seconds, suffix in mapping:
        matching = [
            quota for quota in policy.quotas
            if quota.metric == metric and quota.window_seconds == window_seconds and quota.scope == "account"
        ]
        if not matching:
            continue
        if len(matching) != 1:
            raise SnapshotError(f"Groq policy has an ambiguous {metric}/{window_seconds}s account quota")
        names = (
            f"x-ratelimit-limit-{suffix}",
            f"x-ratelimit-remaining-{suffix}",
            f"x-ratelimit-reset-{suffix}",
        )
        present = [name in normalized for name in names]
        if not any(present):
            continue
        if not all(present):
            missing = [name for name in names if name not in normalized]
            raise SnapshotError("Groq response is missing required headers: " + ", ".join(missing))

        limit = _header_integer(normalized, names[0])
        remaining = _header_integer(normalized, names[1])
        if limit <= 0 or remaining > limit:
            raise SnapshotError(f"Groq {metric} remaining/limit values are inconsistent")
        policy_limit = matching[0].limit
        if limit != policy_limit:
            raise SnapshotError(
                f"Groq {metric} header limit {limit} does not match the policy limit {policy_limit}"
            )
        reset_seconds = _duration_seconds(normalized[names[2]], names[2])
        if reset_seconds > window_seconds:
            raise SnapshotError(f"Groq {metric} reset duration exceeds its {window_seconds}-second window")
        quotas.append({
            "metric": metric,
            "window_seconds": window_seconds,
            "scope": "account",
            "used": limit - remaining,
            "limit": limit,
            "reset_at": _utc_text(captured + reset_seconds),
        })

    if not quotas:
        raise SnapshotError(
            "No supported Groq quota headers matched the policy; configure account requests/86400 "
            "and/or combined tokens/60 quotas and capture their headers"
        )
    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "provider": policy.provider,
        "model": policy.model,
        "account_scope": account_scope,
        "source_type": "response_headers",
        "source_url": _GROQ_SOURCE_URL,
        "captured_at": _utc_text(captured),
        "quotas": quotas,
    }

