"""Atomic local quota reservations for requests routed through the workshop.

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


class UsageLedgerError(Exception):
    """Raised when quota state cannot be checked or reserved safely."""


class QuotaExceeded(UsageLedgerError):
    """Raised when a proposed request would exceed a configured quota."""


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    metric: str
    scope: str
    window_seconds: int
    limit: int
    used: int
    requested: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def remaining_after_request(self) -> int:
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

    Quota windows are rolling windows. They can be stricter than a provider's
    fixed reset window, but avoid guessing reset time zones or boundaries.
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
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except (OSError, sqlite3.Error) as exc:
            raise UsageLedgerError(f"Could not initialize usage ledger: {exc}") from exc

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
        """Read quota state; this method does not reserve or consume usage."""
        self._validate(account_scope, input_tokens, output_tokens, neurons)
        timestamp = self._timestamp(now)
        self._require_neuron_quota(policy, neurons)
        try:
            with self._connection() as db:
                return self._status(db, policy, account_scope, input_tokens,
                                    output_tokens, neurons, int(include_request), timestamp)
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
        """Atomically reserve quota before network I/O. Do not auto-refund errors."""
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
                statuses = self._status(db, policy, account_scope, input_tokens,
                                        output_tokens, neurons, 1, timestamp)
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
        """Read current local usage without proposing a request."""
        return self.check(policy, account_scope=account_scope, now=now)

    def _status(
        self, db: sqlite3.Connection, policy: ModelPolicy, account_scope: str,
        input_tokens: int, output_tokens: int, neurons: int, requests: int, now: float,
    ) -> tuple[QuotaStatus, ...]:
        requested = {
            "requests": requests, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "neurons": neurons,
        }
        result: list[QuotaStatus] = []
        for quota in policy.quotas:
            column = _COLUMNS[quota.metric]
            model_clause = " AND model = ?" if quota.scope == "model" else ""
            params: tuple[object, ...] = (
                policy.provider, account_scope.strip(), now - quota.window_seconds,
            )
            if model_clause:
                params += (policy.model,)
            row = db.execute(
                f"SELECT COALESCE(SUM({column}), 0) FROM usage_events "
                f"WHERE provider = ? AND account_scope = ? AND reserved_at >= ?{model_clause}",
                params,
            ).fetchone()
            result.append(QuotaStatus(
                quota.metric, quota.scope, quota.window_seconds, quota.limit,
                int(row[0] if row else 0), requested[quota.metric],
            ))
        return tuple(result)

    @staticmethod
    def _raise_if_exceeded(statuses: tuple[QuotaStatus, ...]) -> None:
        exceeded = [item for item in statuses if item.used + item.requested > item.limit]
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
