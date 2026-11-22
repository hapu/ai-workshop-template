from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from workshop.providers.base import Message
from workshop.providers.openrouter import OpenRouterAdapter, ProviderTransportError
from workshop.providers.policy import ModelPolicy, PolicyDenied, ProviderRegistry
from workshop.providers.runner import execute_with_free_tier_gate
from workshop.providers.usage_ledger import UsageLedger


class FakeHTTPResponse:
    def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
        self.raw = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self.raw if size < 0 else self.raw[:size]


def response_payload(model: str = "vendor/model:free") -> dict[str, object]:
    return {
        "id": "gen-test-123",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "Test response"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }


class OpenRouterAdapterTests(unittest.TestCase):
    def test_request_is_pinned_to_one_model_and_disables_provider_fallbacks(self) -> None:
        fake = FakeHTTPResponse(response_payload(), {"X-Generation-Id": "req-123"})
        with patch("workshop.providers.openrouter.urlopen", return_value=fake) as send:
            result = OpenRouterAdapter("test-secret").complete(
                model="vendor/model:free", messages=[Message("user", "hello")], max_output_tokens=64
            )
        request = send.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(body["model"], "vendor/model:free")
        self.assertEqual(body["max_tokens"], 64)
        self.assertEqual(body["provider"], {"allow_fallbacks": False})
        self.assertNotIn("models", body)
        self.assertFalse(body["stream"])
        self.assertEqual(result.text, "Test response")
        self.assertEqual(result.request_id, "req-123")
        self.assertEqual((result.input_tokens, result.output_tokens), (12, 7))
        send.assert_called_once()

    def test_response_id_is_used_when_request_header_is_absent(self) -> None:
        with patch("workshop.providers.openrouter.urlopen", return_value=FakeHTTPResponse(response_payload())):
            result = OpenRouterAdapter("secret").complete(
                model="vendor/model:free", messages=[Message("user", "hello")], max_output_tokens=32
            )
        self.assertEqual(result.request_id, "gen-test-123")

    def test_invalid_input_is_rejected_before_network(self) -> None:
        with patch("workshop.providers.openrouter.urlopen") as send:
            with self.assertRaises(ValueError):
                OpenRouterAdapter("secret").complete(
                    model="vendor/model:free", messages=[], max_output_tokens=10
                )
            with self.assertRaises(ValueError):
                OpenRouterAdapter("secret").complete(
                    model="vendor/model:free", messages=[Message("tool", "no")], max_output_tokens=10
                )
        send.assert_not_called()

    def test_http_error_is_sanitized_and_not_retried(self) -> None:
        error = HTTPError(
            "https://openrouter.ai/api/v1/chat/completions", 402, "payment required", {},
            io.BytesIO(b"secret body"),
        )
        with patch("workshop.providers.openrouter.urlopen", side_effect=error) as send:
            with self.assertRaisesRegex(ProviderTransportError, "HTTP 402") as caught:
                OpenRouterAdapter("do-not-print-this-key").complete(
                    model="vendor/model:free", messages=[Message("user", "hello")], max_output_tokens=10
                )
        self.assertNotIn("do-not-print-this-key", str(caught.exception))
        self.assertNotIn("secret body", str(caught.exception))
        send.assert_called_once()

    def test_network_failure_is_not_retried(self) -> None:
        with patch("workshop.providers.openrouter.urlopen", side_effect=URLError("offline")) as send:
            with self.assertRaisesRegex(ProviderTransportError, "not retried"):
                OpenRouterAdapter("secret").complete(
                    model="vendor/model:free", messages=[Message("user", "hello")], max_output_tokens=10
                )
        send.assert_called_once()

    def test_invalid_response_is_rejected(self) -> None:
        with patch("workshop.providers.openrouter.urlopen", return_value=FakeHTTPResponse({"model": "other", "choices": []})):
            with self.assertRaisesRegex(ProviderTransportError, "did not match"):
                OpenRouterAdapter("secret").complete(
                    model="vendor/model:free", messages=[Message("user", "hello")], max_output_tokens=10
                )

    def test_runner_blocks_missing_policy_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch("workshop.providers.openrouter.urlopen") as send:
            ledger = UsageLedger(Path(temp) / "usage.sqlite3")
            with self.assertRaises(PolicyDenied):
                execute_with_free_tier_gate(
                    OpenRouterAdapter("secret"), registry=ProviderRegistry(), ledger=ledger,
                    model="vendor/model:free", messages=[Message("user", "hello")],
                    input_tokens=10, max_output_tokens=10, region="MX", account_scope="test-account",
                )
        send.assert_not_called()

    def test_runner_reserves_before_openrouter_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            policy = ModelPolicy.from_dict({
                "provider": "openrouter", "model": "vendor/model:free", "enabled": True,
                "access_type": "free_tier", "verification_status": "verified",
                "verified_at": "2026-11-20", "expires_at": "2027-02-18",
                "source_url": "https://openrouter.ai/models", "terms_url": "https://openrouter.ai/terms",
                "regions": ["MX"], "input_cost_usd_per_million_tokens": 0,
                "output_cost_usd_per_million_tokens": 0, "max_input_tokens": 2000,
                "max_output_tokens": 500,
                "quotas": [{"metric": "requests", "window_seconds": 3600, "limit": 5, "scope": "account"}],
            })
            registry = ProviderRegistry([policy])
            ledger = UsageLedger(Path(temp) / "usage.sqlite3")
            now = time.time()
            captured = datetime.fromtimestamp(now - 1, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            reset = datetime.fromtimestamp(now + 3599, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            ledger.import_snapshot({
                "schema_version": 1, "snapshot_id": uuid.uuid4().hex,
                "provider": "openrouter", "model": "vendor/model:free", "account_scope": "openrouter-account",
                "source_type": "manual", "source_url": "https://openrouter.ai/account",
                "captured_at": captured,
                "quotas": [{"metric": "requests", "window_seconds": 3600, "scope": "account",
                            "used": 0, "limit": 5, "reset_at": reset}],
            }, policy)

            def send_after_reservation(request, timeout):
                status = ledger.usage(policy, account_scope="openrouter-account")[0]
                self.assertEqual(status.local_used, 1)
                return FakeHTTPResponse(response_payload())

            with patch("workshop.providers.openrouter.urlopen", side_effect=send_after_reservation) as send:
                result = execute_with_free_tier_gate(
                    OpenRouterAdapter("secret"), registry=registry, ledger=ledger,
                    model="vendor/model:free", messages=[Message("user", "hello")],
                    input_tokens=20, max_output_tokens=40, region="MX",
                    account_scope="openrouter-account",
                )
            self.assertEqual(result.response.text, "Test response")
            send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
