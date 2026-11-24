from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workshop.proposal_apply.filesystem import (
    FilesystemSafetyError,
    open_private_directory_at,
    open_repository_root,
    read_private_file_at,
    fsync_directory,
)
from workshop.proposal_apply.journal import JournalError, read_journal, seal_journal, verify_journal
from workshop.proposal_apply.recovery import RecoveryInventoryError, inventory_transaction
from workshop.proposal_apply.transaction import (
    PreparationError,
    OperationRequest,
    prepare_proposal_transaction,
    prepare_transaction,
    repository_identity,
    snapshot_operation,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ProposalTransactionPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.repository = base / "repo"
        (self.repository / "docs").mkdir(parents=True)
        (self.repository / "docs" / "note.txt").write_bytes(b"original note")
        (self.repository / "docs" / "old.txt").write_bytes(b"remove me")
        self.root_fd = open_repository_root(self.repository)
        self.addCleanup(os.close, self.root_fd)

        self.proposal_id = "a" * 32
        self.state_dir = base / "state"
        self.state_dir.mkdir(mode=0o700)
        self.state_dir.chmod(0o700)
        self.state_fd = os.open(self.state_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.state_fd)
        proposals_dir = self.state_dir / "proposals"
        proposals_dir.mkdir(mode=0o700)
        proposals_dir.chmod(0o700)
        self.proposal_dir = proposals_dir / self.proposal_id
        self.proposal_dir.mkdir(mode=0o700)
        self.proposal_dir.chmod(0o700)
        self.proposal_fd = os.open(self.proposal_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.proposal_fd)
        self.repository_record = repository_identity(self.repository, self.root_fd)

    def _prepared_operations(self):
        return (
            snapshot_operation(
                self.root_fd, "update", "docs/note.txt", digest(b"original note"), b"updated note"
            ),
            snapshot_operation(
                self.root_fd, "create", "docs/new.txt", None, b"new file"
            ),
            snapshot_operation(
                self.root_fd, "delete", "docs/old.txt", digest(b"remove me"), None
            ),
        )

    def _requests(self):
        return (
            OperationRequest("update", "docs/note.txt", digest(b"original note"), b"updated note"),
            OperationRequest("create", "docs/new.txt", None, b"new file"),
            OperationRequest("delete", "docs/old.txt", digest(b"remove me"), None),
        )

    def _prepare(self):
        return prepare_proposal_transaction(
            self.state_fd,
            self.proposal_fd,
            repository_path=self.repository,
            repository_root_fd=self.root_fd,
            proposal_id=self.proposal_id,
            proposal_sha256="b" * 64,
            operations=self._requests(),
            transaction_id="c" * 32,
        )

    def _open_transaction(self, transaction_id: str = "c" * 32) -> int:
        transactions_fd = open_private_directory_at(self.proposal_fd, "transactions")
        try:
            return open_private_directory_at(transactions_fd, transaction_id)
        finally:
            os.close(transactions_fd)

    def test_snapshot_and_prepare_leave_all_repository_targets_unchanged(self) -> None:
        before = {
            "docs/note.txt": (self.repository / "docs/note.txt").read_bytes(),
            "docs/old.txt": (self.repository / "docs/old.txt").read_bytes(),
        }
        prepared = self._prepare()
        self.assertEqual(prepared.state, "PREPARED")
        self.assertTrue((self.state_dir / f"proposal-{self.proposal_id}.lock").exists())
        self.assertTrue((self.state_dir / "repository.lock").exists())
        self.assertEqual((self.repository / "docs/note.txt").read_bytes(), before["docs/note.txt"])
        self.assertEqual((self.repository / "docs/old.txt").read_bytes(), before["docs/old.txt"])
        self.assertFalse((self.repository / "docs/new.txt").exists())

    def test_journal_contains_validated_operations_and_private_payloads(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            journal = read_journal(transaction_fd)
            self.assertEqual(journal["state"], "PREPARED")
            self.assertEqual([item["op"] for item in journal["operations"]], ["update", "create", "delete"])
            backups_fd = open_private_directory_at(transaction_fd, "backups")
            prepared_fd = open_private_directory_at(transaction_fd, "prepared")
            try:
                self.assertEqual(read_private_file_at(backups_fd, "0001.bin"), b"original note")
                self.assertEqual(read_private_file_at(backups_fd, "0003.bin"), b"remove me")
                self.assertEqual(read_private_file_at(prepared_fd, "0001.bin"), b"updated note")
                self.assertEqual(read_private_file_at(prepared_fd, "0002.bin"), b"new file")
            finally:
                os.close(backups_fd)
                os.close(prepared_fd)
        finally:
            os.close(transaction_fd)

    def test_recovery_inventory_is_read_only_and_reports_original_targets(self) -> None:
        prepared = self._prepare()
        inventory = inventory_transaction(
            self.proposal_fd, prepared.transaction_id, repository_root_fd=self.root_fd, repository_root_path=self.repository
        )
        self.assertEqual(inventory["state"], "PREPARED")
        self.assertTrue(inventory["repository_identity_matches"])
        self.assertTrue(inventory["private_artifacts_verified"])
        states = {item["path"]: item["state"] for item in inventory["targets"]}
        self.assertEqual(states["docs/note.txt"], "regular_file")
        self.assertEqual(states["docs/old.txt"], "regular_file")
        self.assertEqual(states["docs/new.txt"], "absent")
        target_states = {item["path"]: item for item in inventory["targets"]}
        self.assertTrue(target_states["docs/note.txt"]["matches_known_transaction_state"])
        self.assertTrue(target_states["docs/new.txt"]["matches_original_state"])
        self.assertTrue(target_states["docs/old.txt"]["matches_original_identity"])
        self.assertEqual((self.repository / "docs/note.txt").read_bytes(), b"original note")
        self.assertEqual((self.repository / "docs/old.txt").read_bytes(), b"remove me")
        self.assertFalse((self.repository / "docs/new.txt").exists())

    def test_inventory_rejects_a_different_repository_identity(self) -> None:
        prepared = self._prepare()
        other = Path(self.temp.name) / "other"
        other.mkdir()
        other_fd = open_repository_root(other)
        try:
            inventory = inventory_transaction(
                self.proposal_fd, prepared.transaction_id, repository_root_fd=other_fd, repository_root_path=other
            )
            self.assertFalse(inventory["repository_identity_matches"])
            self.assertIsNone(inventory["targets"])
            self.assertTrue(inventory["private_artifacts_verified"])
        finally:
            os.close(other_fd)

    def test_inventory_reports_missing_backup_without_modifying_target(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            backups_fd = open_private_directory_at(transaction_fd, "backups")
            try:
                os.unlink("0003.bin", dir_fd=backups_fd)
            finally:
                os.close(backups_fd)
        finally:
            os.close(transaction_fd)
        inventory = inventory_transaction(
            self.proposal_fd, prepared.transaction_id, repository_root_fd=self.root_fd, repository_root_path=self.repository
        )
        self.assertEqual(inventory["missing_backups"], ["0003.bin"])
        self.assertFalse(inventory["private_artifacts_verified"])
        self.assertEqual((self.repository / "docs/old.txt").read_bytes(), b"remove me")

    def test_inventory_reports_missing_preparation_directories(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            for directory_name in ("backups", "prepared"):
                directory_fd = open_private_directory_at(transaction_fd, directory_name)
                try:
                    for filename in os.listdir(directory_fd):
                        os.unlink(filename, dir_fd=directory_fd)
                finally:
                    os.close(directory_fd)
                os.rmdir(directory_name, dir_fd=transaction_fd)
        finally:
            os.close(transaction_fd)
        inventory = inventory_transaction(self.proposal_fd, prepared.transaction_id)
        self.assertEqual(inventory["missing_transaction_entries"], ["backups", "prepared"])
        self.assertFalse(inventory["private_artifacts_verified"])
    def test_journal_tampering_is_rejected(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            journal_path = self.proposal_dir / "transactions" / prepared.transaction_id / "journal.json"
            journal_path.write_bytes(journal_path.read_bytes() + b" ")
            with self.assertRaises(JournalError):
                read_journal(transaction_fd)
        finally:
            os.close(transaction_fd)
        with self.assertRaises(RecoveryInventoryError):
            inventory_transaction(self.proposal_fd, prepared.transaction_id)

    def test_journal_rejects_malformed_state_and_protected_paths(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            journal = read_journal(transaction_fd)
            malformed_state = dict(journal)
            malformed_state["state"] = []
            with self.assertRaises(JournalError):
                verify_journal(malformed_state)
            protected_path = dict(journal)
            protected_path["operations"] = [dict(item) for item in journal["operations"]]
            protected_path["operations"][0]["path"] = ".git/config"
            with self.assertRaises(JournalError):
                seal_journal(protected_path)
        finally:
            os.close(transaction_fd)

    def test_inventory_reports_unexpected_private_artifacts(self) -> None:
        prepared = self._prepare()
        transaction_fd = self._open_transaction(prepared.transaction_id)
        try:
            backups_fd = open_private_directory_at(transaction_fd, "backups")
            try:
                extra = self.proposal_dir / "transactions" / prepared.transaction_id / "backups" / "unexpected.bin"
                extra.write_bytes(b"unrecorded")
                extra.chmod(0o600)
            finally:
                os.close(backups_fd)
        finally:
            os.close(transaction_fd)
        inventory = inventory_transaction(self.proposal_fd, prepared.transaction_id)
        self.assertEqual(inventory["unexpected_backups"], ["unexpected.bin"])
        self.assertFalse(inventory["private_artifacts_verified"])

    def test_failed_preparation_leaves_a_preparing_journal_and_targets_unchanged(self) -> None:
        with patch("workshop.proposal_apply.transaction.create_private_file_at",
                   side_effect=OSError("simulated private storage failure")):
            with self.assertRaises(OSError):
                prepare_proposal_transaction(
                    self.state_fd,
                    self.proposal_fd,
                    repository_path=self.repository,
                    repository_root_fd=self.root_fd,
                    proposal_id=self.proposal_id,
                    proposal_sha256="b" * 64,
                    operations=self._requests(),
                    transaction_id="d" * 32,
                )
        transaction_fd = self._open_transaction("d" * 32)
        try:
            self.assertEqual(read_journal(transaction_fd)["state"], "PREPARING")
        finally:
            os.close(transaction_fd)
        self.assertEqual((self.repository / "docs/note.txt").read_bytes(), b"original note")
        self.assertFalse((self.repository / "docs/new.txt").exists())

    def test_existing_transaction_id_cannot_be_reused(self) -> None:
        self._prepare()
        with self.assertRaises(FilesystemSafetyError):
            prepare_transaction(
                self.proposal_fd, proposal_id=self.proposal_id,
                proposal_sha256="b" * 64, repository=self.repository_record,
                repository_root_fd=self.root_fd, operations=self._prepared_operations(),
                transaction_id="c" * 32,
            )

    def test_repository_identity_must_match_open_root_descriptor(self) -> None:
        other = Path(self.temp.name) / "other-root"
        other.mkdir()
        other_fd = open_repository_root(other)
        try:
            with self.assertRaises(PreparationError):
                prepare_transaction(
                    self.proposal_fd, proposal_id=self.proposal_id,
                    proposal_sha256="b" * 64, repository=self.repository_record,
                    repository_root_fd=other_fd, operations=self._prepared_operations(),
                    transaction_id="e" * 32,
                )
        finally:
            os.close(other_fd)

    def test_snapshot_rejects_stale_hash_and_symlink_target(self) -> None:
        with self.assertRaises(PreparationError):
            snapshot_operation(self.root_fd, "update", "docs/note.txt", "0" * 64, b"new")
        link = self.repository / "docs" / "linked.txt"
        link.symlink_to(self.repository / "docs" / "note.txt")
        with self.assertRaises(PreparationError):
            snapshot_operation(self.root_fd, "update", "docs/linked.txt", digest(b"original note"), b"new")

    def test_directory_fsync_failure_is_explicit(self) -> None:
        with patch("workshop.proposal_apply.filesystem.os.fsync", side_effect=OSError(22, "unsupported")):
            with self.assertRaises(FilesystemSafetyError):
                fsync_directory(self.proposal_fd)


if __name__ == "__main__":
    unittest.main()
