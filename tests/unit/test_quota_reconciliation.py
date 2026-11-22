from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from workshop.providers.policy import ModelPolicy
from workshop.providers.reconciliation import SnapshotError, openrouter_key_response_to_snapshot
from workshop.providers.usage_ledger import (
    ReconciliationRequired,
    UsageLedger,
    UsageLedgerError,
)


def iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def policy_for(model: str = "free-a", quotas: list[dict] | None = None) -> ModelPolicy:
    return ModelPolicy.from_dict({
        "provider": "demo",
        "model": model,
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
        "quotas": quotas or [
            {"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account", "snapshot_max_age_seconds": 30},
            {"metric": "input_tokens", "window_seconds": 60, "limit": 1000, "scope": "account", "snapshot_max_age_seconds": 30},
        ],
    })


def snapshot_for(
    policy: ModelPolicy,
    *,
    account_scope: str = "demo-account",
    captured_at: float = 1000,
    used: dict | None = None,
    source_type: str = "manual",
) -> dict:
    used = used or {}
    return {
        "schema_version": 1,
        "snapshot_id": uuid.uuid4().hex,
        "provider": policy.provider,
        "model": policy.model,
        "account_scope": account_scope,
        "source_type": source_type,
        "source_url": "https://provider.example/dashboard",
        "captured_at": iso(captured_at),
        "quotas": [
            {
                "metric": item.metric,
                "window_seconds": item.window_seconds,
                "scope": item.scope,
                "used": used.get((item.metric, item.window_seconds, item.scope), 0),
                "limit": item.limit,
                "reset_at": iso(captured_at + item.window_seconds),
            }
            for item in policy.quotas
        ],
    }


class QuotaReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = UsageLedger(Path(self.temp.name) / "usage.sqlite3")
        self.policy = policy_for()

    def test_missing_snapshot_blocks_reservation(self) -> None:
        with self.assertRaisesRegex(ReconciliationRequired, "No external quota snapshot"):
            self.ledger.reserve(
                self.policy, account_scope="demo-account",
                input_tokens=10, output_tokens=10, now=1001,
            )

    def test_external_usage_plus_later_local_reservations_is_combined(self) -> None:
        snapshot = snapshot_for(
            self.policy,
            captured_at=1000,
            used={("requests", 60, "account"): 7, ("input_tokens", 60, "account"): 200},
        )
        self.ledger.import_snapshot(snapshot, self.policy, now=1001)
        self.ledger.reserve(
            self.policy, account_scope="demo-account",
            input_tokens=50, output_tokens=20, now=1002,
        )
        statuses = self.ledger.usage(self.policy, account_scope="demo-account", now=1003)
        request_status = next(item for item in statuses if item.metric == "requests")
        token_status = next(item for item in statuses if item.metric == "input_tokens")
        self.assertEqual(request_status.snapshot_used, 7)
        self.assertEqual(request_status.local_used, 1)
        self.assertEqual(request_status.used, 8)
        self.assertEqual(token_status.used, 250)

    def test_missing_one_quota_entry_blocks_entire_request(self) -> None:
        snapshot = snapshot_for(self.policy, captured_at=1000)
        snapshot["quotas"] = snapshot["quotas"][:1]
        self.ledger.import_snapshot(snapshot, self.policy, now=1001)
        with self.assertRaisesRegex(ReconciliationRequired, "input_tokens"):
            self.ledger.reserve(
                self.policy, account_scope="demo-account",
                input_tokens=10, output_tokens=10, now=1001,
            )
        statuses = self.ledger.usage(self.policy, account_scope="demo-account", now=1001)
        self.assertTrue(statuses[0].reconciled)
        self.assertFalse(statuses[1].reconciled)

    def test_stale_snapshot_blocks_new_requests(self) -> None:
        policy = policy_for(quotas=[
            {"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account", "snapshot_max_age_seconds": 5}
        ])
        self.ledger.import_snapshot(snapshot_for(policy, captured_at=1000), policy, now=1001)
        with self.assertRaisesRegex(ReconciliationRequired, "stale"):
            self.ledger.reserve(
                policy, account_scope="demo-account",
                input_tokens=10, output_tokens=10, now=1006,
            )

    def test_snapshot_after_reset_boundary_is_rejected(self) -> None:
        policy = policy_for(quotas=[
            {"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account"}
        ])
        self.ledger.import_snapshot(snapshot_for(policy, captured_at=1000), policy, now=1001)
        with self.assertRaisesRegex(ReconciliationRequired, "expired"):
            self.ledger.reserve(
                policy, account_scope="demo-account",
                input_tokens=10, output_tokens=10, now=1061,
            )

    def test_wrong_policy_limit_is_rejected_on_import(self) -> None:
        snapshot = snapshot_for(self.policy, captured_at=1000)
        snapshot["quotas"][0]["limit"] += 1
        with self.assertRaisesRegex(UsageLedgerError, "does not match"):
            self.ledger.import_snapshot(snapshot, self.policy, now=1001)

    def test_future_capture_and_credentials_are_rejected(self) -> None:
        future = snapshot_for(self.policy, captured_at=2000)
        with self.assertRaisesRegex(UsageLedgerError, "future"):
            self.ledger.import_snapshot(future, self.policy, now=1001)
        with_secret = snapshot_for(self.policy, captured_at=1000)
        with_secret["api_key"] = "sk-test-do-not-store"
        with self.assertRaisesRegex(UsageLedgerError, "credentials"):
            self.ledger.import_snapshot(with_secret, self.policy, now=1001)

    def test_duplicate_snapshot_id_is_rejected(self) -> None:
        snapshot = snapshot_for(self.policy, captured_at=1000)
        self.ledger.import_snapshot(snapshot, self.policy, now=1001)
        with self.assertRaisesRegex(UsageLedgerError, "already imported"):
            self.ledger.import_snapshot(snapshot, self.policy, now=1001)

    def test_account_snapshot_can_apply_to_another_model_with_same_account_policy(self) -> None:
        account_quotas = [{"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account"}]
        first = policy_for("free-a", account_quotas)
        second = policy_for("free-b", account_quotas)
        self.ledger.import_snapshot(snapshot_for(first, captured_at=1000), first, now=1001)
        self.ledger.reserve(second, account_scope="demo-account", input_tokens=1, output_tokens=1, now=1001)

    def test_model_scoped_snapshot_does_not_apply_to_another_model(self) -> None:
        model_quotas = [{"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "model"}]
        first = policy_for("free-a", model_quotas)
        second = policy_for("free-b", model_quotas)
        self.ledger.import_snapshot(snapshot_for(first, captured_at=1000), first, now=1001)
        with self.assertRaisesRegex(ReconciliationRequired, "No external quota snapshot"):
            self.ledger.reserve(second, account_scope="demo-account", input_tokens=1, output_tokens=1, now=1001)


    def test_openrouter_key_response_converts_daily_request_counter(self) -> None:
        policy = policy_for("example/model:free", [
            {"metric": "requests", "window_seconds": 86400, "limit": 50, "scope": "account"}
        ])
        captured = datetime.now(timezone.utc).replace(microsecond=0)
        payload = {"data": {"free_model_daily_requests": {"used": 12, "limit": 50, "remaining": 38}}}
        canonical = openrouter_key_response_to_snapshot(
            payload, policy, account_scope="openrouter-personal",
            captured_at=captured.isoformat().replace("+00:00", "Z"),
            snapshot_id="openrouter-daily-test",
        )
        self.ledger.import_snapshot(canonical, policy)
        status = self.ledger.usage(policy, account_scope="openrouter-personal")
        self.assertEqual(status[0].snapshot_used, 12)
        self.assertEqual(status[0].snapshot_source_type, "api")
        self.assertEqual(status[0].snapshot_source_url, "https://openrouter.ai/api/v1/key")

    def test_openrouter_counter_requires_exact_verified_daily_limit(self) -> None:
        policy = policy_for("example/model:free", [
            {"metric": "requests", "window_seconds": 86400, "limit": 50, "scope": "account"}
        ])
        payload = {"data": {"free_model_daily_requests": {"used": 12, "limit": 100, "remaining": 88}}}
        with self.assertRaisesRegex(SnapshotError, "does not match the policy"):
            openrouter_key_response_to_snapshot(
                payload, policy, account_scope="openrouter-personal",
                captured_at="2026-11-21T12:00:00Z", snapshot_id="wrong-limit",
            )

    def test_openrouter_import_requires_a_daily_account_request_policy(self) -> None:
        policy = policy_for("example/model:free", [
            {"metric": "requests", "window_seconds": 60, "limit": 20, "scope": "account"}
        ])
        payload = {"data": {"free_model_daily_requests": {"used": 1, "limit": 20, "remaining": 19}}}
        with self.assertRaisesRegex(SnapshotError, "86400-second"):
            openrouter_key_response_to_snapshot(
                payload, policy, account_scope="openrouter-personal",
                captured_at="2026-11-21T12:00:00Z", snapshot_id="wrong-window",
            )


    def test_cli_reconcile_openrouter_key_response(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            root = Path(work_dir)
            catalog = root / "catalog.json"
            response_path = root / "openrouter-key.json"
            ledger_path = root / "usage.sqlite3"
            raw_policy = {
                "provider": "openrouter", "model": "example/model:free", "enabled": True,
                "access_type": "free_tier", "verification_status": "verified",
                "verified_at": "2026-11-20", "expires_at": "2027-02-18",
                "source_url": "https://openrouter.ai/collections/free-models",
                "terms_url": "https://openrouter.ai/terms", "regions": ["MX"],
                "input_cost_usd_per_million_tokens": 0,
                "output_cost_usd_per_million_tokens": 0,
                "max_input_tokens": 5000, "max_output_tokens": 1000,
                "quotas": [
                    {"metric": "requests", "window_seconds": 86400, "limit": 50,
                     "scope": "account", "snapshot_max_age_seconds": 300}
                ],
            }
            catalog.write_text(json.dumps({"schema_version": 1, "models": [raw_policy]}), encoding="utf-8")
            response_path.write_text(json.dumps({
                "data": {"free_model_daily_requests": {"used": 9, "limit": 50, "remaining": 41}}
            }), encoding="utf-8")
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            captured = iso(time.time() - 1)
            result = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "reconcile-openrouter-key",
                 str(response_path), "--model", "example/model:free",
                 "--account-scope", "openrouter-personal", "--captured-at", captured,
                 "--catalog", str(catalog), "--ledger", str(ledger_path)],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("Imported OpenRouter quota snapshot", result.stdout)
            self.assertIn("Only the OpenRouter free-model daily request counter", result.stdout)
            policy = ModelPolicy.from_dict(raw_policy)
            status = UsageLedger(ledger_path).usage(policy, account_scope="openrouter-personal")
            self.assertEqual(status[0].snapshot_used, 9)

    def test_cli_reconcile_imports_snapshot_without_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            root = Path(work_dir)
            catalog = root / "catalog.json"
            ledger = root / "usage.sqlite3"
            snapshot_path = root / "snapshot.json"
            raw_policy = {
                "provider": "demo", "model": "free-a", "enabled": True,
                "access_type": "free_tier", "verification_status": "verified",
                "verified_at": "2026-11-20", "expires_at": "2027-02-18",
                "source_url": "https://provider.example/pricing",
                "terms_url": "https://provider.example/terms", "regions": ["MX"],
                "input_cost_usd_per_million_tokens": 0,
                "output_cost_usd_per_million_tokens": 0,
                "max_input_tokens": 5000, "max_output_tokens": 1000,
                "quotas": [
                    {"metric": "requests", "window_seconds": 86400, "limit": 50, "scope": "account"}
                ],
            }
            policy = ModelPolicy.from_dict(raw_policy)
            now = time.time()
            raw_snapshot = snapshot_for(
                policy, captured_at=now - 1,
                used={("requests", 86400, "account"): 12},
            )
            raw_snapshot["quotas"][0]["reset_at"] = iso(now + 3600)
            catalog.write_text(json.dumps({"schema_version": 1, "models": [raw_policy]}), encoding="utf-8")
            snapshot_path.write_text(json.dumps(raw_snapshot), encoding="utf-8")
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            result = subprocess.run(
                [sys.executable, "-m", "workshop", "provider", "reconcile", str(snapshot_path),
                 "--catalog", str(catalog), "--ledger", str(ledger)],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("Imported quota snapshot", result.stdout)
            self.assertIn("No API request was made", result.stdout)
            status = UsageLedger(ledger).usage(policy, account_scope="demo-account")
            self.assertTrue(status[0].reconciled)
            self.assertEqual(status[0].snapshot_used, 12)


if __name__ == "__main__":
    unittest.main()
