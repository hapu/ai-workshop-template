from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from workshop.providers.policy import (
    FreeTierGate,
    PolicyDenied,
    ProviderCatalogError,
    ProviderRegistry,
)


class ProviderPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = {
            "provider": "example",
            "model": "example-free-model",
            "enabled": True,
            "access_type": "free_tier",
            "verification_status": "verified",
            "verified_at": "2026-11-20",
            "expires_at": "2027-02-18",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms",
            "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0,
            "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 5000,
            "max_output_tokens": 1000,
        }
        self.today = date(2026, 11, 21)

    def gate(self, data: dict | None = None) -> FreeTierGate:
        from workshop.providers.policy import ModelPolicy
        return FreeTierGate(ProviderRegistry([ModelPolicy.from_dict(data or self.policy)]))

    def authorize(self, gate: FreeTierGate | None = None, **overrides):
        args = {
            "provider": "example",
            "model": "example-free-model",
            "input_tokens": 1200,
            "output_tokens": 400,
            "region": "MX",
            "today": self.today,
        }
        args.update(overrides)
        return (gate or self.gate()).authorize(**args)

    def test_all_verified_zero_cost_conditions_allow_preflight(self) -> None:
        result = self.authorize()
        self.assertEqual(result.provider, "example")
        self.assertEqual(result.estimated_cost_usd, 0)
        self.assertEqual(result.region, "MX")

    def test_unknown_model_is_denied(self) -> None:
        with self.assertRaisesRegex(PolicyDenied, "No verified policy"):
            self.authorize(self.gate(), model="not-listed")

    def test_expired_policy_is_denied(self) -> None:
        data = {**self.policy, "expires_at": "2026-11-20"}
        with self.assertRaisesRegex(PolicyDenied, "expired"):
            self.authorize(self.gate(data))

    def test_future_verification_date_is_denied(self) -> None:
        data = {**self.policy, "verified_at": "2026-11-22"}
        with self.assertRaisesRegex(PolicyDenied, "future"):
            self.authorize(self.gate(data))

    def test_paid_trial_disabled_or_unverified_models_are_denied(self) -> None:
        for changes in (
            {"access_type": "trial"},
            {"enabled": False},
            {"verification_status": "unverified"},
            {"input_cost_usd_per_million_tokens": 0.01},
            {"output_cost_usd_per_million_tokens": 0.01},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PolicyDenied):
                    self.authorize(self.gate({**self.policy, **changes}))

    def test_region_and_token_limits_are_enforced(self) -> None:
        with self.assertRaisesRegex(PolicyDenied, "Region"):
            self.authorize(region="US")
        with self.assertRaisesRegex(PolicyDenied, "input tokens"):
            self.authorize(input_tokens=5001)
        with self.assertRaisesRegex(PolicyDenied, "output tokens"):
            self.authorize(output_tokens=1001)

    def test_invalid_source_or_terms_urls_are_denied(self) -> None:
        for field in ("source_url", "terms_url"):
            data = {**self.policy, field: "http://insecure.example/page"}
            with self.subTest(field=field):
                with self.assertRaisesRegex(PolicyDenied, "HTTPS"):
                    self.authorize(self.gate(data))

    def test_missing_catalog_fails_closed(self) -> None:
        registry = ProviderRegistry.load(Path(tempfile.gettempdir()) / "missing-provider-catalog.json")
        with self.assertRaises(PolicyDenied):
            self.authorize(FreeTierGate(registry))

    def test_catalog_rejects_duplicate_models(self) -> None:
        from workshop.providers.policy import ModelPolicy
        model = ModelPolicy.from_dict(self.policy)
        with self.assertRaisesRegex(ProviderCatalogError, "Duplicate model"):
            ProviderRegistry([model, model])

    def test_catalog_rejects_boolean_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            catalog = Path(work_dir) / "catalog.json"
            catalog.write_text(json.dumps({"schema_version": True, "models": []}), encoding="utf-8")
            with self.assertRaisesRegex(ProviderCatalogError, "integer schema_version"):
                ProviderRegistry.load(catalog)

    def test_catalog_rejects_expiry_before_verification(self) -> None:
        from workshop.providers.policy import ModelPolicy
        data = {**self.policy, "verified_at": "2026-11-21", "expires_at": "2026-11-20"}
        with self.assertRaisesRegex(ProviderCatalogError, "cannot precede"):
            ModelPolicy.from_dict(data)

    def test_cli_preflight_denies_without_a_verified_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            catalog = Path(work_dir) / "catalog.json"
            catalog.write_text(json.dumps({"schema_version": 1, "models": []}), encoding="utf-8")
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            result = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "preflight", "example", "model",
                 "--input-tokens", "10", "--output-tokens", "10", "--region", "MX",
                 "--catalog", str(catalog)],
                capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("DENIED", result.stderr)


if __name__ == "__main__":
    unittest.main()
