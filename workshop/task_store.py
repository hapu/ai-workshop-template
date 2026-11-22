"""Small, dependency-free JSON persistence for workshop tasks."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .models import TASK_STATUSES, Task, utc_now

_TASK_ID = re.compile(r"^[a-f0-9]{8}$")


class TaskStoreError(Exception):
    """Raised when a task cannot be created, read, or updated safely."""


class TaskStore:
    """Store task files beneath a configurable local workspace directory."""

    def __init__(self, home: Path | str = ".workshop") -> None:
        self.home = Path(home).expanduser().resolve()
        self.tasks_dir = self.home / "tasks"

    def create(self, title: str, description: str = "", project_path: Path | str = ".") -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise TaskStoreError("Task title cannot be empty")
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(5):
            task_id = uuid.uuid4().hex[:8]
            path = self._path_for(task_id)
            if not path.exists():
                task = Task.create(task_id, clean_title, description, Path(project_path))
                self._write(task)
                return task
        raise TaskStoreError("Could not allocate a unique task ID")

    def get(self, task_id: str) -> Task:
        path = self._path_for(task_id)
        if not path.is_file():
            raise TaskStoreError(f"Task not found: {task_id}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Task JSON must contain an object")
            task = Task.from_dict(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise TaskStoreError(f"Could not read task {task_id}: {exc}") from exc
        if task.id != task_id:
            raise TaskStoreError(f"Task ID mismatch in file: {task_id}")
        return task

    def list(self) -> list[Task]:
        if not self.tasks_dir.exists():
            return []
        tasks: list[Task] = []
        for path in sorted(self.tasks_dir.glob("*.json"), reverse=True):
            task = self.get(path.stem)
            tasks.append(task)
        return sorted(tasks, key=lambda item: item.updated_at, reverse=True)

    def set_status(self, task_id: str, status: str) -> Task:
        if status not in TASK_STATUSES:
            choices = ", ".join(sorted(TASK_STATUSES))
            raise TaskStoreError(f"Invalid status '{status}'. Choose from: {choices}")
        task = self.get(task_id)
        task.status = status
        task.updated_at = utc_now()
        self._write(task)
        return task

    def add_note(self, task_id: str, note: str) -> Task:
        clean_note = note.strip()
        if not clean_note:
            raise TaskStoreError("Note cannot be empty")
        task = self.get(task_id)
        task.notes.append(clean_note)
        task.updated_at = utc_now()
        self._write(task)
        return task

    def _path_for(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise TaskStoreError("Task ID must be an eight-character lowercase hexadecimal ID")
        return self.tasks_dir / f"{task_id}.json"

    def _write(self, task: Task) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        destination = self._path_for(task.id)
        temporary = destination.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(task.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise TaskStoreError(f"Could not save task {task.id}: {exc}") from exc
