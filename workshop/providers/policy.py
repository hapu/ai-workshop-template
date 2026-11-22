"""Fail-closed provider catalog parsing and free-tier preflight authorization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ProviderCatalogError(Exception):
    """Raised when a provider catalog is malformed or unsafe to interpret."""


class PolicyDenied(Exception):
    """Raised when a model request cannot be proven eligible for zero-cost use."""


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    provider: str
    model: str
    enabled: bool
    access_type: str
    verification_status: str
    verified_at: date
    expires_at: date
    source_url: str
    terms_url: str
    regions: tuple[str, ...]
    input_cost_usd_per_million_tokens: Decimal
    output_cost_usd_per_million_tokens: Decimal
    max_input_tokens: int
    max_output_tokens: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ModelPolicy":
        required = {
            "provider", "model", "enabled", "access_type", "verification_status",
            "verified_at", "expires_at", "source_url", "terms_url", "regions",
            "input_cost_usd_per_million_tokens", "output_cost_usd_per_million_tokens",
            "max_input_tokens", "max_output_tokens",
        }
        missing = required.difference(raw)
        if missing:
            raise ProviderCatalogError(
                "Model policy is missing fields: " + ", ".join(sorted(missing))
            )
        for field_name in ("provider", "model", "access_type", "verification_status", "source_url", "terms_url"):
            if not isinstance(raw[field_name], str) or not raw[field_name].strip():
                raise ProviderCatalogError(f"Model policy field '{field_name}' must be a non-empty string")
        if not isinstance(raw["enabled"], bool):
            raise ProviderCatalogError("Model policy field 'enabled' must be boolean")
        regions = raw["regions"]
        if not isinstance(regions, list) or not regions or not all(isinstance(item, str) and item.strip() for item in regions):
            raise ProviderCatalogError("Model policy 'regions' must be a non-empty list of region codes")
        for field_name in ("max_input_tokens", "max_output_tokens"):
            value = raw[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ProviderCatalogError(f"Model policy field '{field_name}' must be a positive integer")
        try:
            verified = date.fromisoformat(raw["verified_at"])
            expires = date.fromisoformat(raw["expires_at"])
            input_cost = Decimal(str(raw["input_cost_usd_per_million_tokens"]))
            output_cost = Decimal(str(raw["output_cost_usd_per_million_tokens"]))
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise ProviderCatalogError(f"Invalid date or cost in model policy: {exc}") from exc
        if input_cost < 0 or output_cost < 0:
            raise ProviderCatalogError("Model costs cannot be negative")
        if expires < verified:
            raise ProviderCatalogError("Policy expiry date cannot precede its verification date")
        return cls(
            provider=raw["provider"].strip().lower(),
            model=raw["model"].strip(),
            enabled=raw["enabled"],
            access_type=raw["access_type"].strip().lower(),
            verification_status=raw["verification_status"].strip().lower(),
            verified_at=verified,
            expires_at=expires,
            source_url=raw["source_url"].strip(),
            terms_url=raw["terms_url"].strip(),
            regions=tuple(item.strip().upper() for item in regions),
            input_cost_usd_per_million_tokens=input_cost,
            output_cost_usd_per_million_tokens=output_cost,
            max_input_tokens=raw["max_input_tokens"],
            max_output_tokens=raw["max_output_tokens"],
        )


class ProviderRegistry:
    """Load the locally maintained, evidence-backed model allowlist."""

    def __init__(self, policies: list[ModelPolicy] | None = None) -> None:
        self._policies: dict[tuple[str, str], ModelPolicy] = {}
        for policy in policies or []:
            key = (policy.provider, policy.model)
            if key in self._policies:
                raise ProviderCatalogError(f"Duplicate model policy: {policy.provider}/{policy.model}")
            self._policies[key] = policy

    @classmethod
    def load(cls, path: Path | str = "config/provider-catalog.json") -> "ProviderRegistry":
        catalog_path = Path(path).expanduser()
        if not catalog_path.exists():
            return cls([])
        try:
            raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderCatalogError(f"Could not read provider catalog: {exc}") from exc
        if (
            not isinstance(raw, dict)
            or isinstance(raw.get("schema_version"), bool)
            or raw.get("schema_version") != 1
        ):
            raise ProviderCatalogError("Provider catalog must be an object with integer schema_version 1")
        models = raw.get("models")
        if not isinstance(models, list) or not all(isinstance(item, dict) for item in models):
            raise ProviderCatalogError("Provider catalog 'models' must be a list of objects")
        return cls([ModelPolicy.from_dict(item) for item in models])

    def list_models(self) -> list[ModelPolicy]:
        return sorted(self._policies.values(), key=lambda item: (item.provider, item.model))

    def require(self, provider: str, model: str) -> ModelPolicy:
        key = (provider.strip().lower(), model.strip())
        try:
            return self._policies[key]
        except KeyError as exc:
            raise PolicyDenied(f"No verified policy exists for {key[0]}/{key[1]}; request denied") from exc


@dataclass(frozen=True, slots=True)
class PreflightApproval:
    provider: str
    model: str
    region: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal = Decimal("0")


class FreeTierGate:
    """Authorize only explicitly verified, unexpired, zero-priced model policies."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def authorize(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        region: str,
        today: date | None = None,
    ) -> PreflightApproval:
        policy = self.registry.require(provider, model)
        current_date = today or date.today()
        if not policy.enabled:
            raise PolicyDenied("Model is disabled in the local policy catalog")
        if policy.access_type != "free_tier":
            raise PolicyDenied("Model is not explicitly classified as a free tier")
        if policy.verification_status != "verified":
            raise PolicyDenied("Free-tier eligibility is not verified")
        if policy.verified_at > current_date:
            raise PolicyDenied("Policy verification date is in the future")
        if policy.expires_at < current_date:
            raise PolicyDenied("Free-tier verification has expired; verify official terms again")
        for label, value in (("source_url", policy.source_url), ("terms_url", policy.terms_url)):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc:
                raise PolicyDenied(f"A valid HTTPS {label} is required")
        if policy.input_cost_usd_per_million_tokens != 0 or policy.output_cost_usd_per_million_tokens != 0:
            raise PolicyDenied("Model pricing is not exactly zero; request denied")
        clean_region = region.strip().upper()
        if not clean_region or clean_region not in policy.regions:
            raise PolicyDenied(f"Region '{region}' is not explicitly approved for this model")
        for label, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PolicyDenied(f"{label} must be a non-negative integer")
        if input_tokens > policy.max_input_tokens:
            raise PolicyDenied("Estimated input tokens exceed the verified model limit")
        if output_tokens > policy.max_output_tokens:
            raise PolicyDenied("Requested output tokens exceed the verified model limit")
        if input_tokens + output_tokens == 0:
            raise PolicyDenied("Empty inference request denied")
        return PreflightApproval(
            provider=policy.provider,
            model=policy.model,
            region=clean_region,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
