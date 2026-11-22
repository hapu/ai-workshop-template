"""Data models used by the local workshop task store."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_STATUSES = frozenset({"new", "planned", "in_progress", "blocked", "done", "cancelled"})
CHECKPOINT_STATUSES = frozenset({"pending", "done"})


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Checkpoint:
    """A small, independently completable step within a task."""

    id: str
    title: str
    status: str
    created_at: str
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Checkpoint":
        required = {"id", "title", "status", "created_at"}
        missing = required.difference(raw)
        if missing:
            raise ValueError(f"Checkpoint is missing fields: {', '.join(sorted(missing))}")
        for name in required:
            if not isinstance(raw[name], str):
                raise ValueError(f"Checkpoint field '{name}' must be a string")
        completed_at = raw.get("completed_at")
        if completed_at is not None and not isinstance(completed_at, str):
            raise ValueError("Checkpoint completed_at must be a string or null")
        checkpoint = cls(
            id=raw["id"],
            title=raw["title"],
            status=raw["status"],
            created_at=raw["created_at"],
            completed_at=completed_at,
        )
        if checkpoint.status not in CHECKPOINT_STATUSES:
            raise ValueError(f"Invalid checkpoint status: {checkpoint.status}")
        if checkpoint.status == "done" and not checkpoint.completed_at:
            raise ValueError("Completed checkpoint must have completed_at")
        if checkpoint.status == "pending" and checkpoint.completed_at is not None:
            raise ValueError("Pending checkpoint cannot have completed_at")
        return checkpoint


@dataclass(slots=True)
class Task:
    """A persisted unit of work for an AI-assisted development session."""

    id: str
    title: str
    description: str
    status: str
    project_path: str
    created_at: str
    updated_at: str
    notes: list[str] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        task_id: str,
        title: str,
        description: str,
        project_path: Path,
    ) -> "Task":
        now = utc_now()
        return cls(
            id=task_id,
            title=title.strip(),
            description=description.strip(),
            status="new",
            project_path=str(project_path.resolve()),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        """Build a task from JSON data, accepting records created before checkpoints existed."""
        required = {
            "id", "title", "description", "status", "project_path",
            "created_at", "updated_at",
        }
        missing = required.difference(raw)
        if missing:
            raise ValueError(f"Task record is missing fields: {', '.join(sorted(missing))}")
        for name in required:
            if not isinstance(raw[name], str):
                raise ValueError(f"Task field '{name}' must be a string")
        notes = raw.get("notes", [])
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            raise ValueError("Task notes must be a list of strings")
        raw_checkpoints = raw.get("checkpoints", [])
        if not isinstance(raw_checkpoints, list) or not all(isinstance(item, dict) for item in raw_checkpoints):
            raise ValueError("Task checkpoints must be a list of objects")
        task = cls(
            id=raw["id"],
            title=raw["title"],
            description=raw["description"],
            status=raw["status"],
            project_path=raw["project_path"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            notes=notes,
            checkpoints=[Checkpoint.from_dict(item) for item in raw_checkpoints],
        )
        if task.status not in TASK_STATUSES:
            raise ValueError(f"Invalid task status: {task.status}")
        return task

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
