from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import time
import uuid
from datetime import date, datetime, timezone
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
            "quotas": [
                {"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account"},
                {"metric": "requests", "window_seconds": 86400, "limit": 50, "scope": "account"},
                {"metric": "input_tokens", "window_seconds": 60, "limit": 10000, "scope": "account"},
            ],
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

    def test_catalog_requires_quota_entries(self) -> None:
        from workshop.providers.policy import ModelPolicy
        data = {**self.policy, "quotas": []}
        with self.assertRaisesRegex(ProviderCatalogError, "non-empty list"):
            ModelPolicy.from_dict(data)

    def test_catalog_rejects_invalid_or_duplicate_quota_entries(self) -> None:
        from workshop.providers.policy import ModelPolicy
        invalid = {**self.policy, "quotas": [{"metric": "requests", "window_seconds": 60, "limit": True, "scope": "account"}]}
        with self.assertRaisesRegex(ProviderCatalogError, "positive integer"):
            ModelPolicy.from_dict(invalid)
        duplicated = {**self.policy, "quotas": [self.policy["quotas"][0], self.policy["quotas"][0]]}
        with self.assertRaisesRegex(ProviderCatalogError, "Duplicate quota"):
            ModelPolicy.from_dict(duplicated)

    def test_cli_preflight_reads_local_usage_without_reserving(self) -> None:
        from workshop.providers.policy import ModelPolicy
        from workshop.providers.usage_ledger import UsageLedger

        with tempfile.TemporaryDirectory() as work_dir:
            root = Path(work_dir)
            catalog = root / "catalog.json"
            ledger_path = root / "usage.sqlite3"
            limited_policy = {
                **self.policy,
                "quotas": [
                    {"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"},
                    {"metric": "requests", "window_seconds": 86400, "limit": 1, "scope": "account"},
                ],
            }
            catalog.write_text(json.dumps({"schema_version": 1, "models": [limited_policy]}), encoding="utf-8")
            policy = ModelPolicy.from_dict(limited_policy)
            now = time.time()
            to_text = lambda value: datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            snapshot = {
                "schema_version": 1, "snapshot_id": uuid.uuid4().hex,
                "provider": "example", "model": "example-free-model",
                "account_scope": "my-project", "source_type": "manual",
                "source_url": "https://provider.example/dashboard",
                "captured_at": to_text(now - 1),
                "quotas": [
                    {"metric": quota["metric"], "window_seconds": quota["window_seconds"],
                     "scope": quota["scope"], "used": 0, "limit": quota["limit"],
                     "reset_at": to_text(now - 1 + quota["window_seconds"])}
                    for quota in limited_policy["quotas"]
                ],
            }
            ledger = UsageLedger(ledger_path)
            ledger.import_snapshot(snapshot, policy, now=now)
            ledger.reserve(
                policy, account_scope="my-project", input_tokens=100,
                output_tokens=50, now=now,
            )
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            denied = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "preflight", "example", "example-free-model",
                 "--input-tokens", "100", "--output-tokens", "50", "--region", "MX",
                 "--account-scope", "my-project", "--catalog", str(catalog), "--ledger", str(ledger_path)],
                capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertEqual(denied.returncode, 2)
            self.assertIn("Quota exceeded", denied.stderr)
            usage = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "usage", "example", "example-free-model",
                 "--account-scope", "my-project", "--catalog", str(catalog), "--ledger", str(ledger_path)],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("1/1 used", usage.stdout)

    def test_cli_preflight_does_not_reserve_a_request(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            root = Path(work_dir)
            catalog = root / "catalog.json"
            ledger_path = root / "usage.sqlite3"
            catalog.write_text(json.dumps({"schema_version": 1, "models": [self.policy]}), encoding="utf-8")
            from workshop.providers.policy import ModelPolicy
            from workshop.providers.usage_ledger import UsageLedger
            policy = ModelPolicy.from_dict(self.policy)
            now = time.time()
            to_text = lambda value: datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            snapshot = {
                "schema_version": 1, "snapshot_id": uuid.uuid4().hex,
                "provider": "example", "model": "example-free-model",
                "account_scope": "default", "source_type": "manual",
                "source_url": "https://provider.example/dashboard",
                "captured_at": to_text(now - 1),
                "quotas": [
                    {"metric": quota["metric"], "window_seconds": quota["window_seconds"],
                     "scope": quota["scope"], "used": 0, "limit": quota["limit"],
                     "reset_at": to_text(now - 1 + quota["window_seconds"])}
                    for quota in self.policy["quotas"]
                ],
            }
            UsageLedger(ledger_path).import_snapshot(snapshot, policy, now=now)
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            result = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "preflight", "example", "example-free-model",
                 "--input-tokens", "100", "--output-tokens", "50", "--region", "MX",
                 "--catalog", str(catalog), "--ledger", str(ledger_path)],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("APPROVED", result.stdout)
            self.assertIn("Preflight does not reserve", result.stdout)
            usage = UsageLedger(ledger_path).usage(policy, account_scope="default")
            self.assertEqual(next(item for item in usage if item.metric == "requests" and item.window_seconds == 60).used, 0)

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
