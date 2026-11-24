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

    def test_new_staged_record_binds_repository_identity_and_opens_securely(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "payload",
        }))
        record = json.loads((staged.directory / "proposal.json").read_text(encoding="utf-8"))
        self.assertEqual(record["version"], 2)
        self.assertEqual(record["repository_identity"]["root"], str(self.root.resolve()))
        state_fd, proposal_fd, root_fd, loaded, operations = self.store.open_for_apply(staged.proposal_id)
        try:
            self.assertEqual(loaded["record_sha256"], record["record_sha256"])
            self.assertEqual(operations[0].path, "new.txt")
            self.assertFalse((self.root / "new.txt").exists())
        finally:
            import os
            for descriptor in (proposal_fd, root_fd, state_fd):
                os.close(descriptor)

    def test_apply_loader_rejects_tampered_record(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "payload",
        }))
        record_path = staged.directory / "proposal.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["source"] = "tampered"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "integrity check failed"):
            self.store.open_for_apply(staged.proposal_id)

    def test_apply_loader_rejects_repository_replacement(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "payload",
        }))
        moved = self.root.with_name("repo-moved")
        self.root.rename(moved)
        self.root.mkdir()
        with self.assertRaisesRegex(ProposalError, "Repository identity changed"):
            self.store.open_for_apply(staged.proposal_id)

    def test_legacy_staged_record_remains_previewable_but_not_applicable(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "payload",
        }))
        record_path = staged.directory / "proposal.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record.pop("repository_identity")
        record["version"] = 1
        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        record["record_sha256"] = hashlib.sha256(canonical).hexdigest()
        record_path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        self.assertIn("staged_read_only", self.store.preview(staged.proposal_id))
        with self.assertRaisesRegex(ProposalError, "predates repository identity"):
            self.store.open_for_apply(staged.proposal_id)

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

    def test_preview_recomputes_diff_instead_of_trusting_stored_text(self) -> None:
        (self.root / "note.txt").write_bytes(b"old")
        staged = self.store.stage(bundle({
            "op": "update", "path": "note.txt", "expected_sha256": hashlib.sha256(b"old").hexdigest(),
            "content": "new",
        }))
        record_path = staged.directory / "proposal.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["previews"][0]["diff"] = "FORGED: no changes"
        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        record["record_sha256"] = hashlib.sha256(canonical).hexdigest()
        record_path.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        preview = self.store.preview(staged.proposal_id)
        self.assertNotIn("FORGED", preview)
        self.assertIn("-old", preview)
        self.assertIn("+new", preview)

    def test_preview_rejects_tampered_staging_record(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "safe",
        }))
        record_path = staged.directory / "proposal.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["source"] = "tampered"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "integrity check failed"):
            self.store.preview(staged.proposal_id)

    def test_preview_rejects_file_changed_after_staging(self) -> None:
        target = self.root / "tracked.txt"
        target.write_text("before", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        staged = self.store.stage(bundle({
            "op": "update", "path": "tracked.txt", "expected_sha256": digest,
            "content": "proposed",
        }))
        target.write_text("changed by another process", encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "stale"):
            self.store.preview(staged.proposal_id)

    def test_preview_rejects_create_target_appearing_after_staging(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "new.txt", "expected_sha256": None, "content": "proposed",
        }))
        (self.root / "new.txt").write_text("created elsewhere", encoding="utf-8")
        with self.assertRaisesRegex(ProposalError, "stale"):
            self.store.preview(staged.proposal_id)

    def test_preview_escapes_terminal_control_characters(self) -> None:
        staged = self.store.stage(bundle({
            "op": "create", "path": "safe.txt", "expected_sha256": None,
            "content": "visible\x1b[31mhidden",
        }))
        preview = self.store.preview(staged.proposal_id)
        self.assertIn("\\x1b[31m", preview)
        self.assertNotIn("\x1b[31m", preview)

    def test_stages_task_and_context_provenance(self) -> None:
        payload = json.loads(bundle({
            "op": "create", "path": "note.md", "expected_sha256": None, "content": "x",
        }))
        payload["task_id"] = "a1b2c3d4"
        payload["context_sha256"] = "a" * 64
        staged = self.store.stage(json.dumps(payload))
        preview = self.store.preview(staged.proposal_id)
        self.assertIn("Task ID: a1b2c3d4", preview)
        self.assertIn("Context SHA-256: " + "a" * 64, preview)

    def test_rejects_invalid_task_or_context_provenance(self) -> None:
        payload = json.loads(bundle({
            "op": "create", "path": "note.md", "expected_sha256": None, "content": "x",
        }))
        payload["task_id"] = "../../bad"
        with self.assertRaisesRegex(ProposalError, "task_id"):
            parse_proposal(json.dumps(payload))
        payload.pop("task_id")
        payload["context_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ProposalError, "context_sha256"):
            parse_proposal(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
