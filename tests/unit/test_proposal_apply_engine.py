from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workshop.proposal_apply.apply import ApplyError, apply_prepared_transaction, rollback_transaction
from workshop.proposal_apply.filesystem import open_private_directory_at
from workshop.proposal_apply.journal import read_journal
from workshop.proposal_apply.locking import transaction_locks
from workshop.proposal_apply.transaction import OperationRequest, prepare_proposal_transaction, snapshot_operation
from workshop.proposals import ProposalStore


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle(*operations: dict[str, object]) -> str:
    return json.dumps({
        "format": "ai-workshop-file-proposal",
        "version": 1,
        "source": "unit-test",
        "created_at": "2026-11-23T00:00:00Z",
        "operations": list(operations),
    })


class ProposalApplyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        (self.root / "docs").mkdir(parents=True)
        (self.root / "docs" / "note.txt").write_bytes(b"original note")
        (self.root / "docs" / "old.txt").write_bytes(b"remove me")
        self.home = base / "private-state"
        self.store = ProposalStore(self.root, self.home)
        raw = bundle(
            {"op": "update", "path": "docs/note.txt", "expected_sha256": digest(b"original note"), "content": "updated note"},
            {"op": "create", "path": "docs/new.txt", "expected_sha256": None, "content": "new file"},
            {"op": "delete", "path": "docs/old.txt", "expected_sha256": digest(b"remove me")},
        )
        self.staged = self.store.stage(raw)
        self.state_fd, self.proposal_fd, self.root_fd, self.record, self.operations = (
            self.store.open_for_apply(self.staged.proposal_id)
        )
        self.addCleanup(os.close, self.state_fd)
        self.addCleanup(os.close, self.proposal_fd)
        self.addCleanup(os.close, self.root_fd)
        requests = tuple(
            OperationRequest(item.operation, item.path, item.expected_sha256,
                             item.content.encode("utf-8") if item.content is not None else None)
            for item in self.operations
        )
        self.snapshots = tuple(
            snapshot_operation(
                self.root_fd, item.operation, item.path, item.expected_sha256,
                item.content.encode("utf-8") if item.content is not None else None,
            )
            for item in self.operations
        )
        self.prepared = prepare_proposal_transaction(
            self.state_fd,
            self.proposal_fd,
            repository_path=self.root,
            repository_root_fd=self.root_fd,
            proposal_id=self.staged.proposal_id,
            proposal_sha256=self.record["record_sha256"],
            operations=requests,
        )

    def _apply(self):
        with transaction_locks(self.state_fd, f"proposal-{self.staged.proposal_id}.lock"):
            return apply_prepared_transaction(
                self.proposal_fd,
                self.root_fd,
                self.prepared.transaction_id,
                proposal_id=self.staged.proposal_id,
                proposal_sha256=self.record["record_sha256"],
                repository_root_path=self.root,
                operations=self.operations,
                snapshots=self.snapshots,
            )

    def _journal(self):
        transactions_fd = open_private_directory_at(self.proposal_fd, "transactions")
        try:
            transaction_fd = open_private_directory_at(transactions_fd, self.prepared.transaction_id)
        finally:
            os.close(transactions_fd)
        return transaction_fd

    def test_apply_commits_create_update_and_delete(self) -> None:
        result = self._apply()
        self.assertEqual(result.state, "COMMITTED")
        self.assertEqual((self.root / "docs/note.txt").read_bytes(), b"updated note")
        self.assertEqual((self.root / "docs/new.txt").read_bytes(), b"new file")
        self.assertFalse((self.root / "docs/old.txt").exists())
        transaction_fd = self._journal()
        try:
            self.assertEqual(read_journal(transaction_fd)["state"], "COMMITTED")
        finally:
            os.close(transaction_fd)

    def test_committed_transaction_cannot_be_replayed(self) -> None:
        self._apply()
        with transaction_locks(self.state_fd, f"proposal-{self.staged.proposal_id}.lock"):
            with self.assertRaises(ApplyError):
                apply_prepared_transaction(
                    self.proposal_fd, self.root_fd, self.prepared.transaction_id,
                    proposal_id=self.staged.proposal_id,
                    proposal_sha256=self.record["record_sha256"],
                    repository_root_path=self.root,
                    operations=self.operations,
                    snapshots=self.snapshots,
                )
        self.assertEqual((self.root / "docs/note.txt").read_bytes(), b"updated note")

    def test_stale_target_aborts_before_apply_state_or_writes(self) -> None:
        target = self.root / "docs/note.txt"
        target.write_bytes(b"changed after preparation")
        with transaction_locks(self.state_fd, f"proposal-{self.staged.proposal_id}.lock"):
            with self.assertRaises(ApplyError):
                apply_prepared_transaction(
                    self.proposal_fd, self.root_fd, self.prepared.transaction_id,
                    proposal_id=self.staged.proposal_id,
                    proposal_sha256=self.record["record_sha256"],
                    operations=self.operations,
                )
        self.assertEqual(target.read_bytes(), b"changed after preparation")
        transaction_fd = self._journal()
        try:
            self.assertEqual(read_journal(transaction_fd)["state"], "PREPARED")
        finally:
            os.close(transaction_fd)

    def test_unexpected_sibling_collision_aborts_without_target_changes(self) -> None:
        transaction_fd = self._journal()
        try:
            journal = read_journal(transaction_fd)
            quarantine = journal["operations"][0]["quarantine_name"]
        finally:
            os.close(transaction_fd)
        (self.root / "docs" / quarantine).write_text("not ours", encoding="utf-8")
        with transaction_locks(self.state_fd, f"proposal-{self.staged.proposal_id}.lock"):
            with self.assertRaises(ApplyError):
                apply_prepared_transaction(
                    self.proposal_fd, self.root_fd, self.prepared.transaction_id,
                    proposal_id=self.staged.proposal_id,
                    proposal_sha256=self.record["record_sha256"],
                    operations=self.operations,
                )
        self.assertEqual((self.root / "docs/note.txt").read_bytes(), b"original note")
        self.assertEqual((self.root / "docs" / quarantine).read_text(encoding="utf-8"), "not ours")

    def test_failure_after_first_operation_rolls_back_every_target(self) -> None:
        from workshop.proposal_apply import apply as apply_module

        original_link = apply_module.link_file_at

        def fail_create_install(parent_fd: int, source: str, destination: str) -> None:
            if destination == "new.txt":
                raise OSError("injected create-install failure")
            original_link(parent_fd, source, destination)

        with transaction_locks(self.state_fd, f"proposal-{self.staged.proposal_id}.lock"):
            with patch("workshop.proposal_apply.apply.link_file_at", side_effect=fail_create_install):
                with self.assertRaisesRegex(ApplyError, "original files were restored"):
                    apply_prepared_transaction(
                        self.proposal_fd, self.root_fd, self.prepared.transaction_id,
                        proposal_id=self.staged.proposal_id,
                        proposal_sha256=self.record["record_sha256"],
                        operations=self.operations,
                    )
        self.assertEqual((self.root / "docs/note.txt").read_bytes(), b"original note")
        self.assertEqual((self.root / "docs/old.txt").read_bytes(), b"remove me")
        self.assertFalse((self.root / "docs/new.txt").exists())
        transaction_fd = self._journal()
        try:
            journal = read_journal(transaction_fd)
            self.assertEqual(journal["state"], "ROLLED_BACK")
            self.assertEqual(rollback_transaction(transaction_fd, self.root_fd, repository_root_path=self.root)["state"], "ROLLED_BACK")
        finally:
            os.close(transaction_fd)


if __name__ == "__main__":
    unittest.main()
