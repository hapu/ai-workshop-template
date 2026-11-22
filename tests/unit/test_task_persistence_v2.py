from __future__ import annotations

import concurrent.futures
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from workshop.task_store import TaskStore, TaskStoreError


class TaskPersistenceV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / ".workshop"
        self.store = TaskStore(self.home)

    def test_atomic_replace_failure_preserves_previous_task(self) -> None:
        task = self.store.create("Preserve original")
        destination = self.home / "tasks" / f"{task.id}.json"
        before = destination.read_bytes()
        with patch("workshop.task_store.os.replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(TaskStoreError):
                self.store.add_note(task.id, "must not partially replace")
        self.assertEqual(destination.read_bytes(), before)
        self.assertEqual(list((self.home / "tasks").glob(".*.tmp")), [])

    def test_concurrent_writers_do_not_lose_notes(self) -> None:
        task = self.store.create("Concurrent notes")
        notes = [f"note-{index}" for index in range(24)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda note: self.store.add_note(task.id, note), notes))
        self.assertEqual(set(self.store.get(task.id).notes), set(notes))

    def test_concurrent_checkpoint_additions_are_preserved(self) -> None:
        task = self.store.create("Concurrent checkpoints")
        titles = [f"step-{index}" for index in range(20)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda title: self.store.add_checkpoint(task.id, title), titles))
        saved = self.store.get(task.id).checkpoints
        self.assertEqual({item.title for item in saved}, set(titles))
        self.assertEqual(len({item.id for item in saved}), len(titles))

    def test_dead_process_lock_is_recovered(self) -> None:
        task = self.store.create("Stale lock")
        lock = self.home / "tasks" / f".{task.id}.lock"
        lock.write_text(json.dumps({"pid": 999999999}), encoding="ascii")
        self.store.add_note(task.id, "lock recovered")
        self.assertFalse(lock.exists())
        self.assertEqual(self.store.get(task.id).notes, ["lock recovered"])

    def test_export_import_round_trip(self) -> None:
        task = self.store.create("Portable task", "Keep all state")
        self.store.add_note(task.id, "important context")
        task = self.store.add_checkpoint(task.id, "resume here")
        bundle = Path(self.temp.name) / "task.bundle.json"
        self.store.export_bundle(task.id, bundle)
        other = TaskStore(Path(self.temp.name) / "other")
        imported = other.import_bundle(bundle)
        self.assertEqual(imported.to_dict(), self.store.get(task.id).to_dict())

    def test_import_rejects_checksum_tampering(self) -> None:
        task = self.store.create("Tamper detection")
        bundle = Path(self.temp.name) / "tampered.json"
        self.store.export_bundle(task.id, bundle)
        raw = json.loads(bundle.read_text(encoding="utf-8"))
        raw["task"]["title"] = "changed"
        bundle.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(TaskStoreError, "checksum"):
            TaskStore(Path(self.temp.name) / "other").import_bundle(bundle)

    def test_import_never_overwrites_existing_task(self) -> None:
        task = self.store.create("No overwrite")
        bundle = Path(self.temp.name) / "task.json"
        self.store.export_bundle(task.id, bundle)
        with self.assertRaisesRegex(TaskStoreError, "does not overwrite"):
            self.store.import_bundle(bundle)
        self.assertEqual(self.store.get(task.id).title, "No overwrite")

    def test_recovery_removes_only_old_temporary_files(self) -> None:
        tasks_dir = self.home / "tasks"
        tasks_dir.mkdir(parents=True)
        old = tasks_dir / ".abandoned.json.random.tmp"
        recent = tasks_dir / ".active.json.random.tmp"
        old.write_text("partial", encoding="utf-8")
        recent.write_text("partial", encoding="utf-8")
        os.utime(old, (time.time() - 7200, time.time() - 7200))
        self.assertEqual(self.store.recover(older_than_seconds=3600), 1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_import_rejects_unsupported_version_and_oversized_file(self) -> None:
        task = self.store.create("Version validation")
        bundle = Path(self.temp.name) / "version.json"
        self.store.export_bundle(task.id, bundle)
        raw = json.loads(bundle.read_text(encoding="utf-8"))
        raw["version"] = 999
        bundle.write_text(json.dumps(raw), encoding="utf-8")
        other = TaskStore(Path(self.temp.name) / "other")
        with self.assertRaisesRegex(TaskStoreError, "version"):
            other.import_bundle(bundle)
        bundle.write_text(" " * (1_048_577), encoding="utf-8")
        with self.assertRaisesRegex(TaskStoreError, "1 MiB"):
            other.import_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
