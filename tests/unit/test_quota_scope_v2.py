from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from workshop.providers.policy import ModelPolicy
from workshop.providers.usage_ledger import ReconciliationRequired, UsageLedger, QuotaExceeded, UsageLedgerError


def iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


class QuotaScopeV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ledger.sqlite3"
        self.ledger = UsageLedger(self.path)
        self.policy = ModelPolicy.from_dict({
            "provider": "demo", "model": "model-a", "enabled": True,
            "access_type": "free_tier", "verification_status": "verified",
            "verified_at": "2026-11-20", "expires_at": "2027-02-20",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms", "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0, "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 5000, "max_output_tokens": 1000,
            "quotas": [
                {"metric": "requests", "window_seconds": 60, "limit": 10, "scope": "account"},
                {"metric": "tokens", "window_seconds": 60, "limit": 1000, "scope": "organization"},
                {"metric": "input_tokens", "window_seconds": 60, "limit": 10, "scope": "project"},
                {"metric": "output_tokens", "window_seconds": 60, "limit": 500, "scope": "model"},
            ],
        })

    def snapshot(self, *, omit_project=False):
        quotas = [
            {"metric": "requests", "window_seconds": 60, "scope": "account", "used": 0, "limit": 10, "reset_at": iso(1060)},
            {"metric": "tokens", "window_seconds": 60, "scope": "organization", "scope_id": "org-main", "used": 0, "limit": 1000, "reset_at": iso(1060)},
            {"metric": "output_tokens", "window_seconds": 60, "scope": "model", "used": 0, "limit": 500, "reset_at": iso(1060)},
        ]
        if not omit_project:
            quotas.append({"metric": "input_tokens", "window_seconds": 60, "scope": "project", "scope_id": "project-a", "used": 0, "limit": 10, "reset_at": iso(1060)})
        return {
            "schema_version": 1, "snapshot_id": "snapshot-one",
            "provider": "demo", "model": "model-a", "account_scope": "account-main",
            "source_type": "dashboard", "source_url": "https://provider.example/limits",
            "captured_at": iso(1000), "quotas": quotas,
        }

    def scopes(self):
        return {"organization": "org-main", "project": "project-a"}

    def test_all_independent_boundaries_are_checked(self):
        self.ledger.import_snapshot(self.snapshot(), self.policy, now=1001)
        self.ledger.reserve(self.policy, account_scope="account-main", quota_scopes=self.scopes(),
                            input_tokens=10, output_tokens=20, now=1002)
        with self.assertRaises(QuotaExceeded):
            self.ledger.reserve(self.policy, account_scope="account-main", quota_scopes=self.scopes(),
                                input_tokens=1, output_tokens=20, now=1003)

    def test_missing_project_snapshot_denies_entire_request(self):
        self.ledger.import_snapshot(self.snapshot(omit_project=True), self.policy, now=1001)
        with self.assertRaises(ReconciliationRequired):
            self.ledger.reserve(self.policy, account_scope="account-main", quota_scopes=self.scopes(),
                                input_tokens=1, output_tokens=20, now=1002)

    def test_missing_project_binding_denies_request(self):
        self.ledger.import_snapshot(self.snapshot(), self.policy, now=1001)
        with self.assertRaisesRegex(ReconciliationRequired, "Missing project"):
            self.ledger.reserve(self.policy, account_scope="account-main",
                                quota_scopes={"organization": "org-main"},
                                input_tokens=1, output_tokens=20, now=1002)

    def test_snapshot_requires_scope_id_for_project_and_organization(self):
        raw = self.snapshot()
        raw["quotas"][1].pop("scope_id")
        with self.assertRaisesRegex(UsageLedgerError, "requires scope_id"):
            self.ledger.import_snapshot(raw, self.policy, now=1001)



    def test_account_and_model_scope_ids_cannot_be_relabelled(self):
        raw = self.snapshot()
        raw["quotas"][0]["scope_id"] = "different-account"
        with self.assertRaisesRegex(UsageLedgerError, "must match"):
            self.ledger.import_snapshot(raw, self.policy, now=1001)

    def test_project_boundary_aggregates_usage_across_models(self):
        self.ledger.import_snapshot(self.snapshot(), self.policy, now=1001)
        other_raw = self.snapshot()
        other_raw["snapshot_id"] = "snapshot-model-b"
        other_raw["model"] = "model-b"
        other_policy_raw = {
            "provider": "demo", "model": "model-b", "enabled": True,
            "access_type": "free_tier", "verification_status": "verified",
            "verified_at": "2026-11-20", "expires_at": "2027-02-20",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms", "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0, "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 5000, "max_output_tokens": 1000,
            "quotas": [
                {"metric": "requests", "window_seconds": 60, "limit": 10, "scope": "account"},
                {"metric": "tokens", "window_seconds": 60, "limit": 1000, "scope": "organization"},
                {"metric": "input_tokens", "window_seconds": 60, "limit": 10, "scope": "project"},
                {"metric": "output_tokens", "window_seconds": 60, "limit": 500, "scope": "model"},
            ],
        }
        other_policy = ModelPolicy.from_dict(other_policy_raw)
        self.ledger.import_snapshot(other_raw, other_policy, now=1001)
        self.ledger.reserve(self.policy, account_scope="account-main", quota_scopes=self.scopes(),
                            input_tokens=6, output_tokens=20, now=1002)
        with self.assertRaises(QuotaExceeded):
            self.ledger.reserve(other_policy, account_scope="account-main", quota_scopes=self.scopes(),
                                input_tokens=5, output_tokens=20, now=1003)

    def test_concurrent_reservations_share_project_boundary(self):
        from concurrent.futures import ThreadPoolExecutor

        self.ledger.import_snapshot(self.snapshot(), self.policy, now=1001)

        def attempt(index):
            try:
                self.ledger.reserve(
                    self.policy, account_scope="account-main", quota_scopes=self.scopes(),
                    input_tokens=6, output_tokens=10, request_id=f"parallel-{index}", now=1002,
                )
                return True
            except QuotaExceeded:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sum(results), 1)


    def test_legacy_account_scope_is_recorded_even_when_policy_only_uses_project(self):
        project_policy = ModelPolicy.from_dict({
            "provider": "demo", "model": "project-only-model", "enabled": True,
            "access_type": "free_tier", "verification_status": "verified",
            "verified_at": "2026-11-20", "expires_at": "2027-02-20",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms", "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0, "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 5000, "max_output_tokens": 1000,
            "quotas": [{"metric": "requests", "window_seconds": 60, "limit": 10, "scope": "project"}],
        })
        account_policy = ModelPolicy.from_dict({
            "provider": "demo", "model": "account-model", "enabled": True,
            "access_type": "free_tier", "verification_status": "verified",
            "verified_at": "2026-11-20", "expires_at": "2027-02-20",
            "source_url": "https://provider.example/pricing",
            "terms_url": "https://provider.example/terms", "regions": ["MX"],
            "input_cost_usd_per_million_tokens": 0, "output_cost_usd_per_million_tokens": 0,
            "max_input_tokens": 5000, "max_output_tokens": 1000,
            "quotas": [{"metric": "requests", "window_seconds": 60, "limit": 1, "scope": "account"}],
        })
        project_snapshot = {
            "schema_version": 1, "snapshot_id": "project-only-snapshot",
            "provider": "demo", "model": "project-only-model", "account_scope": "shared-account",
            "source_type": "dashboard", "source_url": "https://provider.example/limits",
            "captured_at": iso(1000),
            "quotas": [{"metric": "requests", "window_seconds": 60, "scope": "project",
                        "scope_id": "project-a", "used": 0, "limit": 10, "reset_at": iso(1060)}],
        }
        account_snapshot = {
            "schema_version": 1, "snapshot_id": "account-only-snapshot",
            "provider": "demo", "model": "account-model", "account_scope": "shared-account",
            "source_type": "dashboard", "source_url": "https://provider.example/limits",
            "captured_at": iso(1000),
            "quotas": [{"metric": "requests", "window_seconds": 60, "scope": "account",
                        "used": 0, "limit": 1, "reset_at": iso(1060)}],
        }
        self.ledger.import_snapshot(project_snapshot, project_policy, now=1001)
        self.ledger.import_snapshot(account_snapshot, account_policy, now=1001)
        self.ledger.reserve(project_policy, account_scope="shared-account",
                            quota_scopes={"project": "project-a"},
                            input_tokens=1, output_tokens=1, now=1002)
        with self.assertRaises(QuotaExceeded):
            self.ledger.reserve(account_policy, account_scope="shared-account",
                                input_tokens=1, output_tokens=1, now=1003)

    def test_v1_database_migrates_existing_events_and_snapshots(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(legacy_path)
        db.executescript("""
            CREATE TABLE usage_events (
                request_id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL,
                account_scope TEXT NOT NULL, reserved_at REAL NOT NULL, requests INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, neurons INTEGER NOT NULL
            );
            CREATE TABLE external_quota_snapshots (
                snapshot_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT,
                account_scope TEXT NOT NULL, metric TEXT NOT NULL, scope TEXT NOT NULL,
                window_seconds INTEGER NOT NULL, used INTEGER NOT NULL, limit_value INTEGER NOT NULL,
                captured_at REAL NOT NULL, reset_at REAL NOT NULL, source_type TEXT NOT NULL,
                source_url TEXT NOT NULL, PRIMARY KEY(snapshot_id, metric, window_seconds, scope)
            );
            INSERT INTO usage_events VALUES ('old-event','demo','model-a','account-main',1000,1,10,20,0);
            INSERT INTO external_quota_snapshots VALUES ('old-snapshot','demo',NULL,'account-main','requests','account',60,0,10,1000,1060,'dashboard','https://provider.example/limits');
        """)
        db.commit()
        db.close()
        UsageLedger(legacy_path)
        db = sqlite3.connect(legacy_path)
        version = db.execute("PRAGMA user_version").fetchone()[0]
        scopes = set(db.execute("SELECT scope, scope_id FROM usage_event_scopes WHERE request_id='old-event'"))
        snapshot_scope = db.execute("SELECT scope_id FROM external_quota_snapshots WHERE snapshot_id='old-snapshot'").fetchone()[0]
        db.close()
        self.assertEqual(version, 2)
        self.assertIn(("account", "account-main"), scopes)
        self.assertIn(("model", "model-a"), scopes)
        self.assertEqual(snapshot_scope, "account-main")


if __name__ == "__main__":
    unittest.main()
