from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Sequence

from workshop.providers.base import Message, ProviderResponse
from workshop.providers.policy import ModelPolicy, PolicyDenied, ProviderRegistry
from workshop.providers.runner import execute_with_free_tier_gate
from workshop.providers.usage_ledger import QuotaExceeded, UsageLedger, UsageLedgerError


class FakeProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, model: str, messages: Sequence[Message], max_output_tokens: int) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(provider="fake", model=model, text="test response")


class ProviderRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = UsageLedger(Path(self.temp.name) / "usage.sqlite3")
        self.policy = ModelPolicy.from_dict({
            "provider": "fake", "model": "free-test", "enabled": True,
            "access_type": "free_tier", "verification_status": "verified",
            "verified_at": "2026-11-20", "expires_at": "2027-02-18",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms", "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0,
            "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 2000, "max_output_tokens": 500,
            "quotas": [{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"}],
        })
        self.registry = ProviderRegistry([self.policy])

    def call(self, provider: FakeProvider):
        return execute_with_free_tier_gate(
            provider, registry=self.registry, ledger=self.ledger,
            model="free-test", messages=[Message(role="user", content="test")],
            input_tokens=100, max_output_tokens=100, region="MX",
            account_scope="fake-account",
        )

    def test_runner_reserves_before_provider_call(self) -> None:
        provider = FakeProvider()
        result = self.call(provider)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(result.response.text, "test response")
        self.assertTrue(result.reservation.request_id)

    def test_denied_policy_never_calls_provider(self) -> None:
        provider = FakeProvider()
        with self.assertRaises(PolicyDenied):
            execute_with_free_tier_gate(
                provider, registry=self.registry, ledger=self.ledger,
                model="unknown-model", messages=[Message(role="user", content="test")],
                input_tokens=100, max_output_tokens=100, region="MX",
                account_scope="fake-account",
            )
        self.assertEqual(provider.calls, 0)

    def test_quota_denial_never_calls_provider(self) -> None:
        provider = FakeProvider()
        self.call(provider)
        with self.assertRaises(QuotaExceeded):
            self.call(provider)
        self.assertEqual(provider.calls, 1)

    def test_adapter_identity_mismatch_is_detected_after_call(self) -> None:
        class WrongIdentityProvider(FakeProvider):
            def complete(self, *, model, messages, max_output_tokens):
                self.calls += 1
                return ProviderResponse(provider="other", model=model, text="unexpected")

        provider = WrongIdentityProvider()
        with self.assertRaisesRegex(RuntimeError, "identity"):
            self.call(provider)
        self.assertEqual(self.ledger.usage(self.policy, account_scope="fake-account")[0].used, 1)

    def test_neuron_request_without_configured_neuron_cap_never_calls_adapter(self) -> None:
        provider = FakeProvider()
        with self.assertRaisesRegex(UsageLedgerError, "no Neuron quota"):
            execute_with_free_tier_gate(
                provider, registry=self.registry, ledger=self.ledger,
                model="free-test", messages=[Message(role="user", content="test")],
                input_tokens=100, max_output_tokens=100, region="MX",
                neurons=10, account_scope="fake-account",
            )
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
