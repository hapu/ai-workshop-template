from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workshop.handoff import render_handoff
from workshop.task_store import TaskStore, TaskStoreError


class TaskStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / ".workshop"
        self.store = TaskStore(self.home)

    def test_create_and_reload_task(self) -> None:
        task = self.store.create("  Build CLI  ", "A first slice", self.temp.name)
        loaded = self.store.get(task.id)
        self.assertEqual(loaded.title, "Build CLI")
        self.assertEqual(loaded.description, "A first slice")
        self.assertEqual(loaded.status, "new")
        self.assertEqual(loaded.id, task.id)

    def test_reject_empty_title(self) -> None:
        with self.assertRaises(TaskStoreError):
            self.store.create("   ")

    def test_status_update_and_notes_persist(self) -> None:
        task = self.store.create("Test persistence")
        changed = self.store.set_status(task.id, "in_progress")
        self.assertEqual(changed.status, "in_progress")
        noted = self.store.add_note(task.id, "Tests are passing")
        loaded = self.store.get(task.id)
        self.assertEqual(loaded.notes, ["Tests are passing"])
        self.assertGreaterEqual(loaded.updated_at, task.updated_at)
        self.assertEqual(noted.notes, loaded.notes)

    def test_reject_invalid_status_and_id_path(self) -> None:
        task = self.store.create("Validation")
        with self.assertRaises(TaskStoreError):
            self.store.set_status(task.id, "paid")
        with self.assertRaises(TaskStoreError):
            self.store.get("../../outside")

    def test_list_is_empty_then_contains_created_tasks(self) -> None:
        self.assertEqual(self.store.list(), [])
        first = self.store.create("First")
        second = self.store.create("Second")
        self.assertEqual({task.id for task in self.store.list()}, {first.id, second.id})

    def test_cli_can_create_list_and_export_a_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            home = Path(work_dir) / "state"
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            created = subprocess.run(
                [sys.executable, "-m", "workshop", "--home", str(home), "task", "create",
                 "CLI task", "--description", "Run the end-to-end check"],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            task_id = created.stdout.split()[2].rstrip(":")
            listed = subprocess.run(
                [sys.executable, "-m", "workshop", "--home", str(home), "task", "list"],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn(task_id, listed.stdout)
            output = Path(work_dir) / "handoff.md"
            subprocess.run(
                [sys.executable, "-m", "workshop", "--home", str(home), "task", "handoff",
                 task_id, "--output", str(output)],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("CLI task", output.read_text(encoding="utf-8"))

    def test_rejects_malformed_notes(self) -> None:
        task = self.store.create("Malformed notes")
        path = self.home / "tasks" / f"{task.id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["notes"] = "not-a-list"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(TaskStoreError):
            self.store.get(task.id)

    def test_corrupt_task_is_reported(self) -> None:
        task = self.store.create("Corrupt me")
        path = self.home / "tasks" / f"{task.id}.json"
        path.write_text(json.dumps({"id": task.id}), encoding="utf-8")
        with self.assertRaises(TaskStoreError):
            self.store.get(task.id)

    def test_handoff_contains_task_context_but_no_environment_secrets(self) -> None:
        task = self.store.create("Prepare handoff", "Summarize the next change")
        self.store.add_note(task.id, "Check the current branch first")
        output = render_handoff(self.store.get(task.id))
        self.assertIn("Prepare handoff", output)
        self.assertIn("Summarize the next change", output)
        self.assertIn("Check the current branch first", output)
        self.assertNotIn("API_KEY=", output)


if __name__ == "__main__":
    unittest.main()
