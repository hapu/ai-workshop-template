from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from workshop.proposals import ProposalError, ProposalStore, parse_proposal


def bundle(*operations: dict[str, object]) -> str:
    return json.dumps({
        "format": "ai-workshop-file-proposal",
        "version": 1,
        "source": "browser-assistant",
        "created_at": "2026-11-23T00:00:00Z",
        "operations": list(operations),
    })


class ProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.home = Path(self.temp.name) / "private-state"
        self.store = ProposalStore(self.root, self.home)

    def test_stages_create_and_renders_preview_without_applying(self) -> None:
        raw = bundle({"op": "create", "path": "docs/new.md", "expected_sha256": None,
                      "content": "# Proposed\n"})
        staged = self.store.stage(raw)
        preview = self.store.preview(staged.proposal_id)
        self.assertIn("staged_read_only", preview)
        self.assertIn("+# Proposed", preview)
        self.assertFalse((self.root / "docs/new.md").exists())
        self.assertTrue((staged.directory / "proposal.json").is_file())

    def test_update_requires_current_hash_and_is_read_only(self) -> None:
        target = self.root / "README.md"
        target.write_text("old\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        staged = self.store.stage(bundle({
            "op": "update", "path": "README.md", "expected_sha256": digest,
            "content": "new\n",
        }))
        self.assertIn("-old", self.store.preview(staged.proposal_id))
        self.assertIn("+new", self.store.preview(staged.proposal_id))
        self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_delete_preview_does_not_delete_file(self) -> None:
        target = self.root / "obsolete.txt"
        target.write_text("remove me\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        staged = self.store.stage(bundle({
            "op": "delete", "path": "obsolete.txt", "expected_sha256": digest,
        }))
        self.assertIn("-remove me", self.store.preview(staged.proposal_id))
        self.assertTrue(target.exists())

    def test_rejects_stale_hash(self) -> None:
        target = self.root / "file.txt"
        target.write_text("current", encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "Stale file hash"):
            self.store.stage(bundle({
                "op": "update", "path": "file.txt", "expected_sha256": "0" * 64,
                "content": "proposed",
            }))

    def test_rejects_traversal_absolute_and_windows_paths(self) -> None:
        for path in ("../outside", "/etc/passwd", "C:/Windows/file", "a\\b", "a//b", "./a"):
            with self.subTest(path=path), self.assertRaises(ProposalError):
                self.store.stage(bundle({
                    "op": "create", "path": path, "expected_sha256": None, "content": "x",
                }))

    def test_rejects_protected_and_credential_paths(self) -> None:
        for path in (
            ".git/config", ".workshop/state.json", "secrets/token.txt",
            ".env", ".env.production", "private-key.pem",
            "config/provider-catalog.json",
        ):
            with self.subTest(path=path), self.assertRaises(ProposalError):
                self.store.stage(bundle({
                    "op": "create", "path": path, "expected_sha256": None, "content": "x",
                }))

    def test_rejects_symlink_escape(self) -> None:
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ProposalError):
            self.store.stage(bundle({
                "op": "create", "path": "linked/file.txt",
                "expected_sha256": None, "content": "x",
            }))

    def test_rejects_duplicate_paths_case_insensitively(self) -> None:
        raw = bundle(
            {"op": "create", "path": "Readme.md", "expected_sha256": None, "content": "a"},
            {"op": "create", "path": "README.md", "expected_sha256": None, "content": "b"},
        )
        with self.assertRaisesRegex(ProposalError, "Duplicate"):
            parse_proposal(raw)

    def test_rejects_oversized_bundle_and_file(self) -> None:
        with self.assertRaisesRegex(ProposalError, "256 KiB"):
            parse_proposal(" " * (256 * 1024 + 1))
        with self.assertRaisesRegex(ProposalError, "64 KiB"):
            parse_proposal(bundle({
                "op": "create", "path": "large.txt", "expected_sha256": None,
                "content": "x" * (64 * 1024 + 1),
            }))

    def test_rejects_unknown_fields_and_operations(self) -> None:
        with self.assertRaises(ProposalError):
            parse_proposal(bundle({
                "op": "execute", "path": "x", "expected_sha256": None, "content": "x",
            }))
        with self.assertRaises(ProposalError):
            parse_proposal(bundle({
                "op": "create", "path": "x", "expected_sha256": None,
                "content": "x", "command": "rm -rf /",
            }))

    def test_create_cannot_overwrite_existing_file(self) -> None:
        (self.root / "existing.txt").write_text("safe", encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "already exists"):
            self.store.stage(bundle({
                "op": "create", "path": "existing.txt",
                "expected_sha256": None, "content": "replace",
            }))


if __name__ == "__main__":
    unittest.main()
