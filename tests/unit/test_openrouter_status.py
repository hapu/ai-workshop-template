from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from workshop.providers.openrouter_status import (
    OpenRouterStatusError,
    fetch_openrouter_key_status,
    parse_openrouter_key_status,
)


def payload():
    return {
        "data": {
            "free_model_daily_requests": {"used": 12, "limit": 50, "remaining": 38},
            "limit_remaining": 0.0,
            "budgets": [
                {
                    "scope": "workspace",
                    "limit_usd": 10.0,
                    "spend_usd": 2.0,
                    "remaining_usd": 8.0,
                }
            ],
            "effective_budget": {
                "scope": "workspace",
                "limit_usd": 10.0,
                "spend_usd": 2.0,
                "remaining_usd": 8.0,
            },
        }
    }


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.body


class OpenRouterStatusTests(unittest.TestCase):
    def test_parses_daily_counter_and_budget_summary(self):
        status = parse_openrouter_key_status(payload())
        self.assertEqual(status.daily_requests_used, 12)
        self.assertEqual(status.daily_requests_limit, 50)
        self.assertEqual(status.daily_requests_remaining, 38)
        self.assertEqual(status.key_credit_remaining, 0.0)
        self.assertEqual(status.effective_budget_remaining, 8.0)
        self.assertEqual(status.budget_count, 1)

    def test_rejects_inconsistent_daily_counter(self):
        data = payload()
        data["data"]["free_model_daily_requests"]["remaining"] = 37
        with self.assertRaises(OpenRouterStatusError):
            parse_openrouter_key_status(data)

    def test_rejects_malformed_budget(self):
        data = payload()
        data["data"]["budgets"][0]["remaining_usd"] = "unknown"
        with self.assertRaises(OpenRouterStatusError):
            parse_openrouter_key_status(data)

    def test_rejects_incomplete_budget(self):
        data = payload()
        del data["data"]["budgets"][0]["remaining_usd"]
        with self.assertRaises(OpenRouterStatusError):
            parse_openrouter_key_status(data)

    def test_rejects_missing_credit_limit_field(self):
        data = payload()
        del data["data"]["limit_remaining"]
        with self.assertRaises(OpenRouterStatusError):
            parse_openrouter_key_status(data)

    def test_fetch_uses_bearer_get_and_parses_json(self):
        response = _Response(json.dumps(payload()).encode())
        with patch("workshop.providers.openrouter_status.build_opener") as build:
            build.return_value.open.return_value = response
            result = fetch_openrouter_key_status("secret-test-key")
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/key")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-test-key")
        self.assertEqual(result["data"]["free_model_daily_requests"]["remaining"], 38)
        handler = build.call_args.args[0]
        self.assertEqual(type(handler).__name__, "_NoRedirectHandler")

    def test_missing_key_fails_before_transport(self):
        with patch("workshop.providers.openrouter_status.build_opener") as build:
            with self.assertRaises(OpenRouterStatusError):
                fetch_openrouter_key_status("")
        build.assert_not_called()

    def test_http_error_is_sanitized_and_not_retried(self):
        error = HTTPError(
            "https://openrouter.ai/api/v1/key", 401, "Unauthorized", {},
            io.BytesIO(b'{"error":"secret details"}'),
        )
        with patch("workshop.providers.openrouter_status.build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaisesRegex(OpenRouterStatusError, "HTTP 401"):
                fetch_openrouter_key_status("secret-test-key")
        self.assertEqual(build.return_value.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
