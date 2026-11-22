"""Crash-safe JSON persistence for workshop tasks."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import TASK_STATUSES, Checkpoint, Task, utc_now

_TASK_ID = re.compile(r"^[a-f0-9]{8}$")
_BUNDLE_FORMAT = "ai-workshop-task-bundle"
_BUNDLE_VERSION = 1
_MAX_BUNDLE_BYTES = 1_048_576


class TaskStoreError(Exception):
    """Raised when a task cannot be created, read, or updated safely."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


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
            with self._task_lock(task_id):
                if self._path_for(task_id).exists():
                    continue
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
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise TaskStoreError(f"Could not read task {task_id}: {exc}") from exc
        if task.id != task_id:
            raise TaskStoreError(f"Task ID mismatch in file: {task_id}")
        return task

    def list(self) -> list[Task]:
        if not self.tasks_dir.exists():
            return []
        tasks = [self.get(p.stem) for p in self.tasks_dir.glob("*.json") if _TASK_ID.fullmatch(p.stem)]
        return sorted(tasks, key=lambda item: item.updated_at, reverse=True)

    def set_status(self, task_id: str, status: str) -> Task:
        if status not in TASK_STATUSES:
            raise TaskStoreError(f"Invalid status '{status}'. Choose from: {', '.join(sorted(TASK_STATUSES))}")
        with self._task_lock(task_id):
            task = self.get(task_id)
            task.status, task.updated_at = status, utc_now()
            self._write(task)
            return task

    def add_note(self, task_id: str, note: str) -> Task:
        clean = note.strip()
        if not clean:
            raise TaskStoreError("Note cannot be empty")
        with self._task_lock(task_id):
            task = self.get(task_id)
            task.notes.append(clean)
            task.updated_at = utc_now()
            self._write(task)
            return task

    def add_checkpoint(self, task_id: str, title: str) -> Task:
        clean = title.strip()
        if not clean:
            raise TaskStoreError("Checkpoint title cannot be empty")
        with self._task_lock(task_id):
            task = self.get(task_id)
            ids = {item.id for item in task.checkpoints}
            checkpoint_id = uuid.uuid4().hex[:8]
            while checkpoint_id in ids:
                checkpoint_id = uuid.uuid4().hex[:8]
            task.checkpoints.append(Checkpoint(checkpoint_id, clean, "pending", utc_now()))
            task.updated_at = utc_now()
            self._write(task)
            return task

    def complete_checkpoint(self, task_id: str, checkpoint_id: str) -> Task:
        if not _TASK_ID.fullmatch(checkpoint_id):
            raise TaskStoreError("Checkpoint ID must be an eight-character lowercase hexadecimal ID")
        with self._task_lock(task_id):
            task = self.get(task_id)
            checkpoint = next((item for item in task.checkpoints if item.id == checkpoint_id), None)
            if checkpoint is None:
                raise TaskStoreError(f"Checkpoint not found: {checkpoint_id}")
            if checkpoint.status != "done":
                checkpoint.status, checkpoint.completed_at = "done", utc_now()
                task.updated_at = utc_now()
                self._write(task)
            return task

    def export_bundle(self, task_id: str, output: Path | str) -> Path:
        payload = self.get(task_id).to_dict()
        bundle = {"format": _BUNDLE_FORMAT, "version": _BUNDLE_VERSION, "task": payload,
                  "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
        destination = Path(output).expanduser().resolve()
        try:
            _atomic_write(destination, json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise TaskStoreError(f"Could not export task {task_id}: {exc}") from exc
        return destination

    def import_bundle(self, source: Path | str) -> Task:
        try:
            path = Path(source).expanduser()
            if path.stat().st_size > _MAX_BUNDLE_BYTES:
                raise ValueError("Task bundle exceeds the 1 MiB size limit")
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(bundle, dict) or bundle.get("format") != _BUNDLE_FORMAT or bundle.get("version") != _BUNDLE_VERSION:
                raise ValueError("Unsupported task bundle format or version")
            payload = bundle.get("task")
            if not isinstance(payload, dict):
                raise ValueError("Bundle task must be a JSON object")
            digest = hashlib.sha256(_canonical(payload)).hexdigest()
            if not isinstance(bundle.get("sha256"), str) or not hmac.compare_digest(bundle["sha256"], digest):
                raise ValueError("Task bundle checksum does not match")
            task = Task.from_dict(payload)
            self._path_for(task.id)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise TaskStoreError(f"Could not import task bundle: {exc}") from exc
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        with self._task_lock(task.id):
            if self._path_for(task.id).exists():
                raise TaskStoreError(f"Task already exists: {task.id}; import does not overwrite")
            self._write(task)
        return task

    def recover(self, *, older_than_seconds: int = 86_400) -> int:
        """Delete old abandoned temporary files; incomplete writes are never promoted."""
        if older_than_seconds < 0:
            raise TaskStoreError("Recovery age cannot be negative")
        if not self.tasks_dir.exists():
            return 0
        cutoff, removed = time.time() - older_than_seconds, 0
        for path in self.tasks_dir.glob(".*.tmp"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise TaskStoreError(f"Could not clean abandoned temporary file {path.name}: {exc}") from exc
        return removed

    def _path_for(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise TaskStoreError("Task ID must be an eight-character lowercase hexadecimal ID")
        return self.tasks_dir / f"{task_id}.json"

    @contextmanager
    def _task_lock(self, task_id: str) -> Iterator[None]:
        lock = self.tasks_dir / f".{task_id}.lock"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 10
        fd = None
        while fd is None:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, json.dumps({"pid": os.getpid()}).encode("ascii"))
                    os.fsync(fd)
                except OSError:
                    os.close(fd)
                    fd = None
                    lock.unlink(missing_ok=True)
                    raise
            except FileExistsError:
                self._clear_stale_lock(lock)
                if time.monotonic() >= deadline:
                    raise TaskStoreError(f"Timed out waiting for task lock: {task_id}")
                time.sleep(0.05)
            except OSError as exc:
                raise TaskStoreError(f"Could not acquire task lock {task_id}: {exc}") from exc
        try:
            yield
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    @staticmethod
    def _clear_stale_lock(lock: Path) -> None:
        try:
            data = json.loads(lock.read_text(encoding="ascii"))
            pid = data.get("pid") if isinstance(data, dict) else None
            if not isinstance(pid, int) or pid <= 0:
                stale = time.time() - lock.stat().st_mtime > 60
            else:
                try:
                    os.kill(pid, 0)
                    stale = False
                except ProcessLookupError:
                    stale = True
                except PermissionError:
                    stale = False
            if stale:
                lock.unlink(missing_ok=True)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            try:
                if time.time() - lock.stat().st_mtime > 60:
                    lock.unlink(missing_ok=True)
            except OSError:
                pass

    def _write(self, task: Task) -> None:
        try:
            _atomic_write(self._path_for(task.id), json.dumps(task.to_dict(), indent=2, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise TaskStoreError(f"Could not save task {task.id}: {exc}") from exc
