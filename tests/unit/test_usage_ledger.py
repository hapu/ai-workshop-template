from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import uuid

from workshop.providers.policy import ModelPolicy
from workshop.providers.usage_ledger import QuotaExceeded, UsageLedger, UsageLedgerError


def make_policy(*, model: str = "free-test", quotas: list[dict] | None = None) -> ModelPolicy:
    return ModelPolicy.from_dict({
        "provider": "fake", "model": model, "enabled": True,
        "access_type": "free_tier", "verification_status": "verified",
        "verified_at": "2026-11-20", "expires_at": "2027-02-18",
        "source_url": "https://provider.example/pricing",
        "terms_url": "https://provider.example/terms", "regions": ["MX"],
        "input_cost_usd_per_million_tokens": 0,
        "output_cost_usd_per_million_tokens": 0,
        "max_input_tokens": 5000, "max_output_tokens": 1000,
        "quotas": quotas or [
            {"metric": "requests", "window_seconds": 60, "limit": 3, "scope": "account"},
            {"metric": "input_tokens", "window_seconds": 60, "limit": 1000, "scope": "account"},
        ],
    })


class UsageLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = UsageLedger(Path(self.temp.name) / "usage.sqlite3")
        self.policy = make_policy()

    def seed_snapshot(self, policy, account_scope: str, now: float, used: dict | None = None) -> None:
        captured = now - 1
        to_text = lambda value: datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        raw = {
            "schema_version": 1,
            "snapshot_id": uuid.uuid4().hex,
            "provider": policy.provider,
            "model": policy.model,
            "account_scope": account_scope,
            "source_type": "manual",
            "source_url": "https://provider.example/dashboard",
            "captured_at": to_text(captured),
            "quotas": [
                {
                    "metric": quota.metric,
                    "window_seconds": quota.window_seconds,
                    "scope": quota.scope,
                    "used": (used or {}).get((quota.metric, quota.window_seconds, quota.scope), 0),
                    "limit": quota.limit,
                    "reset_at": to_text(captured + quota.window_seconds),
                }
                for quota in policy.quotas
            ],
        }
        self.ledger.import_snapshot(raw, policy, now=now)

    def reserve(self, **kwargs):
        return self.ledger.reserve(
            self.policy, account_scope="test-account", input_tokens=100,
            output_tokens=50, now=1000, **kwargs,
        )

    def test_reservation_updates_local_usage(self) -> None:
        self.seed_snapshot(self.policy, "test-account", 1000)
        record = self.reserve()
        self.assertTrue(record.request_id)
        values = self.ledger.usage(self.policy, account_scope="test-account", now=1000)
        requests = next(item for item in values if item.metric == "requests")
        tokens = next(item for item in values if item.metric == "input_tokens")
        self.assertEqual(requests.used, 1)
        self.assertEqual(tokens.used, 100)

    def test_preflight_is_read_only(self) -> None:
        self.seed_snapshot(self.policy, "test-account", 1000)
        statuses = self.ledger.preflight(
            self.policy, account_scope="test-account", input_tokens=100,
            output_tokens=50, now=1000,
        )
        self.assertEqual(next(item for item in statuses if item.metric == "requests").used, 0)
        self.assertEqual(self.ledger.usage(self.policy, account_scope="test-account", now=1000)[0].used, 0)

    def test_request_limit_denies_without_partial_insert(self) -> None:
        limited = make_policy(quotas=[{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"}])
        self.seed_snapshot(limited, "a", 1000)
        self.ledger.reserve(limited, account_scope="a", input_tokens=10, output_tokens=10, now=1000)
        with self.assertRaises(QuotaExceeded):
            self.ledger.reserve(limited, account_scope="a", input_tokens=10, output_tokens=10, now=1001)
        self.assertEqual(self.ledger.usage(limited, account_scope="a", now=1001)[0].used, 1)

    def test_model_scoped_quota_is_separate_for_each_model(self) -> None:
        quotas = [{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "model"}]
        limited = make_policy(quotas=quotas)
        other = make_policy(model="other-model", quotas=quotas)
        self.seed_snapshot(limited, "a", 1000)
        self.seed_snapshot(other, "a", 1000)
        self.ledger.reserve(limited, account_scope="a", input_tokens=10, output_tokens=10, now=1000)
        self.ledger.reserve(other, account_scope="a", input_tokens=10, output_tokens=10, now=1000)

    def test_duplicate_request_id_is_rejected(self) -> None:
        self.seed_snapshot(self.policy, "test-account", 1000)
        self.reserve(request_id="fixed-request")
        with self.assertRaisesRegex(UsageLedgerError, "already has"):
            self.reserve(request_id="fixed-request")

    def test_concurrent_reservations_cannot_exceed_last_slot(self) -> None:
        limited = make_policy(quotas=[{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"}])
        self.seed_snapshot(limited, "race", 1000)
        def attempt(index: int) -> str:
            try:
                self.ledger.reserve(limited, account_scope="race", input_tokens=1,
                                    output_tokens=1, request_id=f"request-{index}", now=1000)
                return "reserved"
            except QuotaExceeded:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertCountEqual(results, ["reserved", "denied"])

    def test_neuron_request_requires_explicit_neuron_quota(self) -> None:
        with self.assertRaisesRegex(UsageLedgerError, "no Neuron quota"):
            self.ledger.reserve(self.policy, account_scope="a", input_tokens=1,
                                output_tokens=1, neurons=5, now=1000)

    def test_bad_timestamp_and_negative_units_are_rejected(self) -> None:
        with self.assertRaisesRegex(UsageLedgerError, "valid UTC timestamp"):
            self.ledger.reserve(self.policy, account_scope="a", input_tokens=1,
                                output_tokens=1, now=float("nan"))
        with self.assertRaisesRegex(UsageLedgerError, "non-negative integer"):
            self.ledger.reserve(self.policy, account_scope="a", input_tokens=-1,
                                output_tokens=1, now=1000)

    def test_rolling_window_expires_old_events(self) -> None:
        limited = make_policy(quotas=[{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"}])
        self.seed_snapshot(limited, "a", 1000)
        self.ledger.reserve(limited, account_scope="a", input_tokens=1, output_tokens=1, now=1000)
        self.seed_snapshot(limited, "a", 1061)
        self.ledger.reserve(limited, account_scope="a", input_tokens=1, output_tokens=1, now=1061)
        self.assertEqual(self.ledger.usage(limited, account_scope="a", now=1061)[0].used, 1)


if __name__ == "__main__":
    unittest.main()
