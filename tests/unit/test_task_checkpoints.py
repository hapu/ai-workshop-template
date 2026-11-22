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


class TaskCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / ".workshop"
        self.store = TaskStore(self.home)

    def test_checkpoint_add_complete_and_persist(self) -> None:
        task = self.store.create("Build resumable workflow")
        task = self.store.add_checkpoint(task.id, "Design context format")
        checkpoint = task.checkpoints[0]
        self.assertEqual(checkpoint.status, "pending")
        task = self.store.complete_checkpoint(task.id, checkpoint.id)
        saved = self.store.get(task.id).checkpoints[0]
        self.assertEqual(saved.status, "done")
        self.assertIsNotNone(saved.completed_at)

    def test_completing_checkpoint_is_idempotent(self) -> None:
        task = self.store.create("Idempotency")
        task = self.store.add_checkpoint(task.id, "One step")
        checkpoint_id = task.checkpoints[0].id
        first = self.store.complete_checkpoint(task.id, checkpoint_id)
        second = self.store.complete_checkpoint(task.id, checkpoint_id)
        self.assertEqual(first.checkpoints[0].completed_at, second.checkpoints[0].completed_at)

    def test_rejects_unknown_checkpoint(self) -> None:
        task = self.store.create("Unknown step")
        with self.assertRaises(TaskStoreError):
            self.store.complete_checkpoint(task.id, "deadbeef")

    def test_old_task_json_without_checkpoints_remains_readable(self) -> None:
        task = self.store.create("Legacy task")
        path = self.home / "tasks" / f"{task.id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("checkpoints", None)
        path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = self.store.get(task.id)
        self.assertEqual(loaded.checkpoints, [])

    def test_handoff_includes_pending_and_completed_checkpoints(self) -> None:
        task = self.store.create("Checkpoint handoff")
        task = self.store.add_checkpoint(task.id, "Already completed")
        completed_id = task.checkpoints[0].id
        self.store.complete_checkpoint(task.id, completed_id)
        task = self.store.add_checkpoint(task.id, "Next action")
        markdown = render_handoff(task)
        self.assertIn("[x]", markdown)
        self.assertIn("[ ]", markdown)
        self.assertIn("Continue the first pending checkpoint", markdown)

    def test_cli_checkpoint_and_resume_commands(self) -> None:
        with tempfile.TemporaryDirectory() as work_dir:
            home = Path(work_dir) / "state"
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
            created = subprocess.run(
                [
                    sys.executable, "-m", "workshop", "--home", str(home),
                    "task", "create", "Resume CLI",
                ],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            task_id = created.stdout.split()[2].rstrip(":")
            added = subprocess.run(
                [
                    sys.executable, "-m", "workshop", "--home", str(home),
                    "task", "checkpoint", "add", task_id, "Inspect tests",
                ],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            checkpoint_id = added.stdout.split()[2].rstrip(":")
            resumed = subprocess.run(
                [
                    sys.executable, "-m", "workshop", "--home", str(home),
                    "task", "resume", task_id,
                ],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("Inspect tests", resumed.stdout)
            self.assertIn("1 pending / 1 total", resumed.stdout)
            subprocess.run(
                [
                    sys.executable, "-m", "workshop", "--home", str(home),
                    "task", "checkpoint", "complete", task_id, checkpoint_id,
                ],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            finished = subprocess.run(
                [
                    sys.executable, "-m", "workshop", "--home", str(home),
                    "task", "resume", task_id,
                ],
                check=True, capture_output=True, text=True, env={**os.environ, **env},
            )
            self.assertIn("0 pending / 1 total", finished.stdout)

    def test_rejects_malformed_checkpoint_record(self) -> None:
        task = self.store.create("Invalid checkpoint")
        path = self.home / "tasks" / f"{task.id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["checkpoints"] = [
            {"id": "deadbeef", "title": "Bad", "status": "done", "created_at": "now"}
        ]
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(TaskStoreError):
            self.store.get(task.id)


if __name__ == "__main__":
    unittest.main()
