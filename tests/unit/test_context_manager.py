from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workshop.context_manager import ContextError, ContextManager


class ContextManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_loads_files_in_stable_order_and_renders_bundle(self) -> None:
        (self.root / "AGENTS.md").write_text("Agent rules", encoding="utf-8")
        (self.root / "PROJECT_CONTEXT.md").write_text("Project goal", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "WORKFLOW.md").write_text("Workflow", encoding="utf-8")
        bundle = ContextManager(self.root, max_words=10).build()
        self.assertEqual(
            [item.path for item in bundle.files],
            ["AGENTS.md", "PROJECT_CONTEXT.md", "docs/WORKFLOW.md"],
        )
        self.assertEqual(bundle.total_words, 5)
        self.assertIn("Source: AGENTS.md", bundle.render())

    def test_enforces_per_file_word_limit(self) -> None:
        (self.root / "AGENTS.md").write_text(" ".join(["word"] * 501), encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "AGENTS.md exceeds"):
            ContextManager(self.root).build()

    def test_enforces_total_word_budget(self) -> None:
        (self.root / "AGENTS.md").write_text("one two", encoding="utf-8")
        (self.root / "PROJECT_CONTEXT.md").write_text("three four", encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "exceeds its 3-word budget"):
            ContextManager(self.root, max_words=3).build()

    def test_rejects_symlink_that_escapes_project_root(self) -> None:
        outside = self.root.parent / (self.root.name + "-outside.md")
        outside.write_text("outside context", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        (self.root / "AGENTS.md").symlink_to(outside)
        with self.assertRaisesRegex(ContextError, "escapes project directory"):
            ContextManager(self.root).build()

    def test_ignores_unlisted_files(self) -> None:
        (self.root / ".env").write_text("API_KEY=should-not-be-read", encoding="utf-8")
        (self.root / "README.md").write_text("not part of context", encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "No project context files"):
            ContextManager(self.root).build()

    def test_cli_writes_context_bundle(self) -> None:
        (self.root / "AGENTS.md").write_text("Use lightweight commands", encoding="utf-8")
        output = self.root / ".workshop" / "context.md"
        env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        result = subprocess.run(
            [
                sys.executable, "-m", "workshop", "context", "build",
                "--project", str(self.root), "--max-words", "20", "--output", str(output),
            ],
            check=True, capture_output=True, text=True, env={**os.environ, **env},
        )
        self.assertIn("Wrote context bundle", result.stdout)
        self.assertIn("Use lightweight commands", output.read_text(encoding="utf-8"))

    def test_rejects_missing_project_directory(self) -> None:
        with self.assertRaisesRegex(ContextError, "does not exist"):
            ContextManager(self.root / "missing").build()


if __name__ == "__main__":
    unittest.main()
