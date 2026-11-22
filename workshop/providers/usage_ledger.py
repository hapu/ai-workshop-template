"""Atomic local quota reservations and external quota reconciliation.

Reservations are retained after transport failures because a provider may have
received a request even when the client did not receive its response.
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .policy import ModelPolicy
from .reconciliation import ExternalQuotaSnapshot, SnapshotError


class UsageLedgerError(Exception):
    """Raised when quota state cannot be checked or reserved safely."""


class QuotaExceeded(UsageLedgerError):
    """Raised when a proposed request would exceed a configured quota."""


class ReconciliationRequired(UsageLedgerError):
    """Raised when a fresh external quota snapshot is required before a request."""


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    metric: str
    scope: str
    window_seconds: int
    limit: int
    used: int | None
    requested: int
    snapshot_used: int | None = None
    local_used: int = 0
    snapshot_captured_at: str | None = None
    snapshot_reset_at: str | None = None
    snapshot_age_seconds: int | None = None
    snapshot_source_type: str | None = None
    snapshot_source_url: str | None = None
    reconciled: bool = False

    @property
    def remaining(self) -> int:
        if self.used is None:
            return 0
        return max(0, self.limit - self.used)

    @property
    def remaining_after_request(self) -> int:
        if self.used is None:
            return 0
        return max(0, self.limit - self.used - self.requested)


@dataclass(frozen=True, slots=True)
class UsageReservation:
    request_id: str
    provider: str
    model: str
    account_scope: str
    reserved_at: str
    quotas: tuple[QuotaStatus, ...]


_COLUMNS = {
    "requests": "requests",
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "neurons": "neurons",
}


class UsageLedger:
    """SQLite ledger using BEGIN IMMEDIATE to serialize competing reservations.

    External snapshots establish the provider-reported baseline. Local
    reservations created after capture are added to that baseline, avoiding
    double-counting reservations already reflected in the provider snapshot.
    """

    def __init__(self, path: Path | str = ".workshop/provider-usage.sqlite3") -> None:
        self.path = Path(path).expanduser().resolve()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as db:
                db.execute(
                    """CREATE TABLE IF NOT EXISTS usage_events (
                        request_id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        account_scope TEXT NOT NULL,
                        reserved_at REAL NOT NULL,
                        requests INTEGER NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        neurons INTEGER NOT NULL
                    )"""
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_usage_scope_time "
                    "ON usage_events(provider, account_scope, reserved_at)"
                )
                db.execute(
                    """CREATE TABLE IF NOT EXISTS external_quota_snapshots (
                        snapshot_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT,
                        account_scope TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        window_seconds INTEGER NOT NULL,
                        used INTEGER NOT NULL,
                        limit_value INTEGER NOT NULL,
                        captured_at REAL NOT NULL,
                        reset_at REAL NOT NULL,
                        source_type TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        PRIMARY KEY (snapshot_id, metric, window_seconds, scope)
                    )"""
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_external_quota_lookup "
                    "ON external_quota_snapshots(provider, account_scope, metric, scope, window_seconds, captured_at)"
                )
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except (OSError, sqlite3.Error) as exc:
            raise UsageLedgerError(f"Could not initialize usage ledger: {exc}") from exc

    def import_snapshot(
        self, raw: dict, policy: ModelPolicy, *, now: float | None = None
    ) -> ExternalQuotaSnapshot:
        """Validate and atomically import a provider/dashboard usage snapshot."""
        timestamp = self._timestamp(now)
        try:
            snapshot = ExternalQuotaSnapshot.from_dict(raw, policy, now=timestamp)
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                exists = db.execute(
                    "SELECT 1 FROM external_quota_snapshots WHERE snapshot_id = ? LIMIT 1",
                    (snapshot.snapshot_id,),
                ).fetchone()
                if exists:
                    raise UsageLedgerError(
                        f"Snapshot {snapshot.snapshot_id} was already imported; use a new ID for a new capture"
                    )
                for quota in snapshot.quotas:
                    model_value = snapshot.model if quota.scope == "model" else None
                    db.execute(
                        """INSERT INTO external_quota_snapshots (
                            snapshot_id, provider, model, account_scope, metric, scope,
                            window_seconds, used, limit_value, captured_at, reset_at,
                            source_type, source_url
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            snapshot.snapshot_id, snapshot.provider, model_value,
                            snapshot.account_scope, quota.metric, quota.scope,
                            quota.window_seconds, quota.used, quota.limit,
                            snapshot.captured_at, quota.reset_at,
                            snapshot.source_type, snapshot.source_url,
                        ),
                    )
                db.commit()
            return snapshot
        except UsageLedgerError:
            raise
        except SnapshotError as exc:
            raise UsageLedgerError(str(exc)) from exc
        except (sqlite3.Error, OSError) as exc:
            raise UsageLedgerError(f"Could not import quota snapshot; request remains blocked: {exc}") from exc

    def check(
        self,
        policy: ModelPolicy,
        *,
        account_scope: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        neurons: int = 0,
        include_request: bool = False,
        now: float | None = None,
    ) -> tuple[QuotaStatus, ...]:
        """Check against external snapshots and local reservations; never reserves."""
        self._validate(account_scope, input_tokens, output_tokens, neurons)
        timestamp = self._timestamp(now)
        self._require_neuron_quota(policy, neurons)
        try:
            with self._connection() as db:
                return self._status(
                    db, policy, account_scope, input_tokens, output_tokens, neurons,
                    int(include_request), timestamp, require_reconciliation=True,
                )
        except UsageLedgerError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise UsageLedgerError(f"Could not read quota state; request denied: {exc}") from exc

    def preflight(
        self,
        policy: ModelPolicy,
        *,
        account_scope: str,
        input_tokens: int,
        output_tokens: int,
        neurons: int = 0,
        now: float | None = None,
    ) -> tuple[QuotaStatus, ...]:
        """Check if one additional request fits without reserving it."""
        statuses = self.check(
            policy, account_scope=account_scope, input_tokens=input_tokens,
            output_tokens=output_tokens, neurons=neurons, include_request=True, now=now,
        )
        self._raise_if_exceeded(statuses)
        return statuses

    def reserve(
        self,
        policy: ModelPolicy,
        *,
        account_scope: str,
        input_tokens: int,
        output_tokens: int,
        neurons: int = 0,
        request_id: str | None = None,
        now: float | None = None,
    ) -> UsageReservation:
        """Atomically validate reconciled quota and reserve before network I/O."""
        self._validate(account_scope, input_tokens, output_tokens, neurons)
        self._require_neuron_quota(policy, neurons)
        if request_id is not None and not isinstance(request_id, str):
            raise UsageLedgerError("request_id must be a string")
        rid = uuid.uuid4().hex if request_id is None else request_id.strip()
        if not rid or len(rid) > 120:
            raise UsageLedgerError("request_id must be a non-empty string up to 120 characters")
        timestamp = self._timestamp(now)
        try:
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                # Policy windows are capped at one year; older rows are irrelevant.
                db.execute("DELETE FROM usage_events WHERE reserved_at < ?", (timestamp - 365 * 86400,))
                if db.execute("SELECT 1 FROM usage_events WHERE request_id = ?", (rid,)).fetchone():
                    raise UsageLedgerError("This request_id already has a quota reservation; do not send twice")
                statuses = self._status(
                    db, policy, account_scope, input_tokens, output_tokens, neurons,
                    1, timestamp, require_reconciliation=True,
                )
                self._raise_if_exceeded(statuses)
                db.execute(
                    """INSERT INTO usage_events (
                        request_id, provider, model, account_scope, reserved_at,
                        requests, input_tokens, output_tokens, neurons
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                    (rid, policy.provider, policy.model, account_scope.strip(), timestamp,
                     input_tokens, output_tokens, neurons),
                )
                db.commit()
        except UsageLedgerError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise UsageLedgerError(f"Could not reserve quota; request denied: {exc}") from exc
        return UsageReservation(
            rid, policy.provider, policy.model, account_scope.strip(),
            datetime.fromtimestamp(timestamp, timezone.utc).isoformat(), statuses,
        )

    def usage(
        self, policy: ModelPolicy, *, account_scope: str, now: float | None = None
    ) -> tuple[QuotaStatus, ...]:
        """Show usage; missing or stale snapshots are reported, not treated as zero."""
        self._validate(account_scope, 0, 0, 0)
        timestamp = self._timestamp(now)
        try:
            with self._connection() as db:
                return self._status(
                    db, policy, account_scope, 0, 0, 0, 0, timestamp,
                    require_reconciliation=False,
                )
        except (sqlite3.Error, OSError) as exc:
            raise UsageLedgerError(f"Could not read quota state: {exc}") from exc

    def _status(
        self,
        db: sqlite3.Connection,
        policy: ModelPolicy,
        account_scope: str,
        input_tokens: int,
        output_tokens: int,
        neurons: int,
        requests: int,
        now: float,
        *,
        require_reconciliation: bool,
    ) -> tuple[QuotaStatus, ...]:
        requested = {
            "requests": requests, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "neurons": neurons,
        }
        result: list[QuotaStatus] = []
        for quota in policy.quotas:
            column = _COLUMNS[quota.metric]
            if quota.scope == "account":
                model_clause = "model IS NULL"
                snapshot_params: tuple[object, ...] = (
                    policy.provider, account_scope.strip(), quota.metric, quota.window_seconds,
                )
                event_model_clause = ""
                event_params: tuple[object, ...] = (
                    policy.provider, account_scope.strip(),
                )
            else:
                model_clause = "model = ?"
                snapshot_params = (
                    policy.provider, account_scope.strip(), quota.metric,
                    quota.window_seconds,
                )
                event_model_clause = " AND model = ?"
                event_params = (policy.provider, account_scope.strip(), policy.model)

            snap = db.execute(
                f"""SELECT used, limit_value, captured_at, reset_at, source_type, source_url
                    FROM external_quota_snapshots
                    WHERE provider = ? AND account_scope = ? AND metric = ?
                      AND window_seconds = ? AND scope = ? AND {model_clause}
                      AND captured_at <= ?
                    ORDER BY captured_at DESC LIMIT 1""",
                snapshot_params + (quota.scope,)
                + ((policy.model,) if quota.scope == "model" else ()) + (now,),
            ).fetchone()

            if snap is None:
                if require_reconciliation:
                    raise ReconciliationRequired(
                        f"No external quota snapshot for {quota.metric}/{quota.window_seconds}s/{quota.scope}; "
                        "import a recent provider dashboard/API snapshot before making requests"
                    )
                local_start = now - quota.window_seconds
                row = db.execute(
                    f"SELECT COALESCE(SUM({column}), 0) FROM usage_events "
                    f"WHERE provider = ? AND account_scope = ? AND reserved_at >= ? AND reserved_at <= ?"
                    + event_model_clause,
                    (policy.provider, account_scope.strip(), local_start, now)
                    + ((policy.model,) if quota.scope == "model" else ()),
                ).fetchone()
                result.append(QuotaStatus(
                    quota.metric, quota.scope, quota.window_seconds, quota.limit,
                    None, requested[quota.metric], None, int(row[0] if row else 0),
                    reconciled=False,
                ))
                continue

            used_external, snapshot_limit, captured_at, reset_at, source_type, source_url = snap
            age = int(max(0, now - float(captured_at)))
            if int(snapshot_limit) != quota.limit:
                raise ReconciliationRequired(
                    f"Imported {quota.metric} quota limit no longer matches the policy; refresh the snapshot and policy"
                )
            if float(reset_at) <= now:
                if require_reconciliation:
                    raise ReconciliationRequired(
                        f"External quota snapshot for {quota.metric}/{quota.window_seconds}s has expired; import a fresh snapshot"
                    )
                result.append(QuotaStatus(
                    quota.metric, quota.scope, quota.window_seconds, quota.limit,
                    None, requested[quota.metric], int(used_external), 0,
                    datetime.fromtimestamp(float(captured_at), timezone.utc).isoformat(),
                    datetime.fromtimestamp(float(reset_at), timezone.utc).isoformat(),
                    age, source_type, source_url, False,
                ))
                continue
            if age > quota.snapshot_max_age_seconds:
                if require_reconciliation:
                    raise ReconciliationRequired(
                        f"External quota snapshot for {quota.metric}/{quota.window_seconds}s is stale "
                        f"({age}s old; maximum {quota.snapshot_max_age_seconds}s); import a fresh snapshot"
                    )
                result.append(QuotaStatus(
                    quota.metric, quota.scope, quota.window_seconds, quota.limit,
                    None, requested[quota.metric], int(used_external), 0,
                    datetime.fromtimestamp(float(captured_at), timezone.utc).isoformat(),
                    datetime.fromtimestamp(float(reset_at), timezone.utc).isoformat(),
                    age, source_type, source_url, False,
                ))
                continue

            local_query = (
                f"SELECT COALESCE(SUM({column}), 0) FROM usage_events "
                "WHERE provider = ? AND account_scope = ? AND reserved_at > ? "
                "AND reserved_at <= ? AND reserved_at < ?" + event_model_clause
            )
            local_row = db.execute(
                local_query,
                (policy.provider, account_scope.strip(), float(captured_at), now, float(reset_at))
                + ((policy.model,) if quota.scope == "model" else ()),
            ).fetchone()
            local_used = int(local_row[0] if local_row else 0)
            total_used = int(used_external) + local_used
            result.append(QuotaStatus(
                quota.metric, quota.scope, quota.window_seconds, quota.limit,
                total_used, requested[quota.metric], int(used_external), local_used,
                datetime.fromtimestamp(float(captured_at), timezone.utc).isoformat(),
                datetime.fromtimestamp(float(reset_at), timezone.utc).isoformat(),
                age, source_type, source_url, True,
            ))
        return tuple(result)

    @staticmethod
    def _raise_if_exceeded(statuses: tuple[QuotaStatus, ...]) -> None:
        exceeded = [item for item in statuses if item.used is not None and item.used + item.requested > item.limit]
        if exceeded:
            detail = "; ".join(
                f"{item.metric} over {item.window_seconds}s: "
                f"{item.used}+{item.requested}>{item.limit}"
                for item in exceeded
            )
            raise QuotaExceeded(f"Quota exceeded; request denied ({detail})")

    @staticmethod
    def _require_neuron_quota(policy: ModelPolicy, neurons: int) -> None:
        if neurons > 0 and not any(q.metric == "neurons" for q in policy.quotas):
            raise UsageLedgerError("Neuron usage requested but no Neuron quota is configured; request denied")

    @staticmethod
    def _timestamp(value: float | None) -> float:
        try:
            result = time.time() if value is None else float(value)
            if not math.isfinite(result):
                raise ValueError("timestamp must be finite")
            datetime.fromtimestamp(result, timezone.utc)
            return result
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            raise UsageLedgerError(f"now must be a valid UTC timestamp: {exc}") from exc

    @staticmethod
    def _validate(account_scope: str, input_tokens: int, output_tokens: int, neurons: int) -> None:
        if not isinstance(account_scope, str) or not account_scope.strip() or len(account_scope.strip()) > 120:
            raise UsageLedgerError("account_scope must be a non-empty local identifier up to 120 characters")
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens), ("neurons", neurons)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise UsageLedgerError(f"{name} must be a non-negative integer")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout = 15000")
            yield db
        finally:
            db.close()
