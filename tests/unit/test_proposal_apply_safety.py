from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from workshop.proposal_apply.filesystem import (
    FilesystemSafetyError,
    directory_identity,
    open_directory_at,
    open_existing_parent,
    open_regular_file_at,
    open_repository_root,
    require_posix_support,
)
from workshop.proposal_apply.locking import (
    LockTimeoutError,
    advisory_lock,
    transaction_locks,
)


@unittest.skipUnless(os.name == "posix", "POSIX-only safety primitives")
class ProposalApplyFilesystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "note.txt").write_text("read-only", encoding="utf-8")
        self.root_fd = open_repository_root(self.root)
        self.addCleanup(os.close, self.root_fd)

    def test_required_posix_primitives_are_available(self) -> None:
        require_posix_support()

    def test_root_identity_matches_open_directory(self) -> None:
        identity = directory_identity(self.root_fd)
        info = self.root.stat()
        self.assertEqual(identity.device, info.st_dev)
        self.assertEqual(identity.inode, info.st_ino)

    def test_root_symlink_is_rejected(self) -> None:
        link = Path(self.temp.name) / "root-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(FilesystemSafetyError):
            open_repository_root(link)

    def test_existing_parent_traversal_and_regular_file_open(self) -> None:
        parent_fd = open_existing_parent(self.root_fd, ["docs"])
        try:
            target_fd = open_regular_file_at(parent_fd, "note.txt")
            try:
                self.assertEqual(os.read(target_fd, 100), b"read-only")
            finally:
                os.close(target_fd)
        finally:
            os.close(parent_fd)

    def test_missing_parent_is_rejected(self) -> None:
        with self.assertRaises(FilesystemSafetyError):
            open_existing_parent(self.root_fd, ["missing"])

    def test_symlink_parent_is_rejected(self) -> None:
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(FilesystemSafetyError):
            open_existing_parent(self.root_fd, ["linked"])

    def test_symlink_target_is_rejected(self) -> None:
        (self.root / "linked-file").symlink_to(self.root / "docs" / "note.txt")
        with self.assertRaises(FilesystemSafetyError):
            open_regular_file_at(self.root_fd, "linked-file")

    def test_hard_linked_target_is_rejected(self) -> None:
        os.link(self.root / "docs" / "note.txt", self.root / "hard-link")
        with self.assertRaises(FilesystemSafetyError):
            open_regular_file_at(self.root_fd, "hard-link")

    def test_directory_cannot_be_opened_as_regular_file(self) -> None:
        with self.assertRaises(FilesystemSafetyError):
            open_regular_file_at(self.root_fd, "docs")

    def test_component_validation_rejects_path_syntax(self) -> None:
        for name in ("", ".", "..", "a/b", "a\\\\b"):
            with self.subTest(name=name), self.assertRaises(FilesystemSafetyError):
                open_directory_at(self.root_fd, name)


@unittest.skipUnless(os.name == "posix", "POSIX-only advisory locks")
class ProposalApplyLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.state_fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.state_fd)

    def test_lock_file_is_private_and_created(self) -> None:
        with advisory_lock(self.state_fd, "proposal-a.lock", timeout=0.1):
            info = (self.state / "proposal-a.lock").stat()
            self.assertEqual(info.st_mode & 0o777, 0o600)

    def test_lock_timeout_does_not_acquire_second_lock(self) -> None:
        with advisory_lock(self.state_fd, "same.lock", timeout=0.1):
            started = time.monotonic()
            with self.assertRaises(LockTimeoutError):
                with advisory_lock(self.state_fd, "same.lock", timeout=0.05):
                    self.fail("Second lock acquisition unexpectedly succeeded")
            self.assertGreaterEqual(time.monotonic() - started, 0.04)

    def test_lock_is_released_when_context_exits(self) -> None:
        with advisory_lock(self.state_fd, "release.lock", timeout=0.1):
            pass
        with advisory_lock(self.state_fd, "release.lock", timeout=0.1):
            pass

    def test_lock_symlink_is_rejected(self) -> None:
        outside = self.state / "outside"
        outside.write_text("not a lock", encoding="utf-8")
        (self.state / "linked.lock").symlink_to(outside)
        with self.assertRaises(FilesystemSafetyError):
            with advisory_lock(self.state_fd, "linked.lock", timeout=0.1):
                self.fail("Symlink lock was accepted")

    def test_group_or_world_accessible_lock_is_rejected(self) -> None:
        path = self.state / "broad.lock"
        path.write_text("", encoding="utf-8")
        path.chmod(0o644)
        with self.assertRaises(FilesystemSafetyError):
            with advisory_lock(self.state_fd, "broad.lock", timeout=0.1):
                self.fail("Insecure lock permissions were accepted")

    def test_transaction_locks_use_the_documented_pair(self) -> None:
        with transaction_locks(self.state_fd, "proposal-123.lock", timeout=0.1):
            self.assertTrue((self.state / "proposal-123.lock").exists())
            self.assertTrue((self.state / "repository.lock").exists())

    def test_transaction_lock_names_must_be_distinct(self) -> None:
        with self.assertRaises(ValueError):
            with transaction_locks(self.state_fd, "same.lock", "same.lock", timeout=0.1):
                self.fail("Duplicate lock names were accepted")


if __name__ == "__main__":
    unittest.main()
