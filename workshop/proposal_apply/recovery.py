"""Read-only inventory of prepared transaction state and repository targets."""
from __future__ import annotations

import hashlib
import os
import stat
from typing import Any

from .filesystem import (
    FilesystemSafetyError,
    _verify_private_directory,
    directory_identity,
    open_existing_parent,
    open_private_directory_at,
    open_regular_file_at,
    open_repository_root,
    read_private_file_at,
)
from .journal import JournalError, read_journal


class RecoveryInventoryError(RuntimeError):
    """Raised when transaction state cannot be safely inventoried."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _private_payload_inventory(
    directory_fd: int,
    expected: dict[str, tuple[str, int]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    present = set(os.listdir(directory_fd))
    expected_names = set(expected)
    missing = sorted(expected_names - present)
    unexpected = sorted(present - expected_names)
    verified: list[dict[str, Any]] = []
    for name in sorted(expected_names & present):
        expected_digest, expected_size = expected[name]
        try:
            content = read_private_file_at(directory_fd, name, max_bytes=65536)
            digest = _sha256(content)
            verified.append({
                "name": name,
                "size": len(content),
                "sha256": digest,
                "matches_journal": len(content) == expected_size and digest == expected_digest,
            })
        except (OSError, FilesystemSafetyError) as exc:
            verified.append({"name": name, "matches_journal": False, "error": str(exc)})
    return verified, missing, unexpected


def _target_inventory(repository_root_fd: int, operation: dict[str, Any]) -> dict[str, Any]:
    parts = operation["path"].split("/")
    try:
        parent_fd = open_existing_parent(repository_root_fd, parts[:-1])
    except (OSError, FilesystemSafetyError) as exc:
        return {"path": operation["path"], "state": "unsafe_parent", "error": str(exc)}
    try:
        try:
            before = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return {"path": operation["path"], "state": "absent"}
        except OSError as exc:
            return {"path": operation["path"], "state": "inspection_error", "error": str(exc)}
        if stat.S_ISLNK(before.st_mode):
            return {"path": operation["path"], "state": "symlink"}
        if not stat.S_ISREG(before.st_mode):
            return {"path": operation["path"], "state": "special_or_directory"}
        try:
            descriptor = open_regular_file_at(parent_fd, parts[-1])
        except FilesystemSafetyError as exc:
            return {"path": operation["path"], "state": "unsafe_file", "error": str(exc)}
        try:
            info = os.fstat(descriptor)
            if info.st_size > 65536:
                return {"path": operation["path"], "state": "oversized"}
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > 65536:
                    return {"path": operation["path"], "state": "oversized"}
            after = os.fstat(descriptor)
            content = b"".join(chunks)
            stable = (
                info.st_dev == after.st_dev and info.st_ino == after.st_ino
                and info.st_size == after.st_size and info.st_mtime_ns == after.st_mtime_ns
                and info.st_ctime_ns == after.st_ctime_ns
                and len(content) == after.st_size
            )
            return {
                "path": operation["path"],
                "state": "regular_file" if stable else "changed_during_inspection",
                "size": len(content),
                "sha256": _sha256(content),
                "device": after.st_dev,
                "inode": after.st_ino,
                "mode": stat.S_IMODE(after.st_mode),
            }
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _open_optional_private_directory(transaction_fd: int, name: str) -> int | None:
    try:
        info = os.stat(name, dir_fd=transaction_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise RecoveryInventoryError(f"Transaction entry is not a real directory: {name}")
    return open_private_directory_at(transaction_fd, name)


def inventory_transaction(
    proposal_dir_fd: int,
    transaction_id: str,
    *,
    repository_root_fd: int | None = None,
    repository_root_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Inspect private transaction artifacts and optionally current targets.

    This function is strictly read-only. It never repairs, deletes, renames,
    creates, or overwrites transaction or repository files.
    """
    _verify_private_directory(proposal_dir_fd)
    if (not isinstance(transaction_id, str) or len(transaction_id) != 32
            or any(char not in "0123456789abcdef" for char in transaction_id)):
        raise RecoveryInventoryError("Invalid transaction ID")

    transactions_fd = open_private_directory_at(proposal_dir_fd, "transactions")
    try:
        transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
    finally:
        os.close(transactions_fd)
    try:
        try:
            journal = read_journal(transaction_fd)
        except (OSError, FilesystemSafetyError, JournalError) as exc:
            raise RecoveryInventoryError(f"Cannot verify transaction journal: {exc}") from exc
        if journal["transaction_id"] != transaction_id:
            raise RecoveryInventoryError("Transaction ID does not match journal identity")

        expected_backups: dict[str, tuple[str, int]] = {}
        expected_prepared: dict[str, tuple[str, int]] = {}
        for operation in journal["operations"]:
            if operation["backup_file"] is not None:
                expected_backups[operation["backup_file"]] = (
                    operation["original_sha256"], operation["backup_size"]
                )
            if operation["prepared_file"] is not None:
                expected_prepared[operation["prepared_file"]] = (
                    operation["proposed_sha256"], operation["prepared_size"]
                )

        backups_fd = _open_optional_private_directory(transaction_fd, "backups")
        prepared_fd = _open_optional_private_directory(transaction_fd, "prepared")
        try:
            if backups_fd is None:
                backups, missing_backups, unexpected_backups = [], sorted(expected_backups), []
            else:
                backups, missing_backups, unexpected_backups = _private_payload_inventory(
                    backups_fd, expected_backups
                )
            if prepared_fd is None:
                prepared, missing_prepared, unexpected_prepared = [], sorted(expected_prepared), []
            else:
                prepared, missing_prepared, unexpected_prepared = _private_payload_inventory(
                    prepared_fd, expected_prepared
                )
        finally:
            if backups_fd is not None:
                os.close(backups_fd)
            if prepared_fd is not None:
                os.close(prepared_fd)

        expected_root_entries = {"journal.json", "backups", "prepared"}
        actual_root_entries = set(os.listdir(transaction_fd))
        missing_transaction_entries = sorted(expected_root_entries - actual_root_entries)
        unexpected_root_entries = sorted(actual_root_entries - expected_root_entries)
        identity_matches: bool | None = None
        target_states: list[dict[str, Any]] | None = None
        if (repository_root_fd is None) != (repository_root_path is None):
            raise RecoveryInventoryError("Provide both the repository root descriptor and its path")
        if repository_root_fd is not None and repository_root_path is not None:
            actual_identity = directory_identity(repository_root_fd)
            recorded = journal["repository_identity"]
            supplied_path = os.path.abspath(os.fspath(repository_root_path))
            verified_fd = open_repository_root(supplied_path)
            try:
                path_identity = directory_identity(verified_fd)
            finally:
                os.close(verified_fd)
            identity_matches = (
                supplied_path == recorded["root"]
                and actual_identity.device == recorded["device"]
                and actual_identity.inode == recorded["inode"]
                and path_identity.device == recorded["device"]
                and path_identity.inode == recorded["inode"]
            )
            if identity_matches:
                target_states = []
                for operation in journal["operations"]:
                    observed = _target_inventory(repository_root_fd, operation)
                    if observed["state"] == "absent":
                        observed["matches_original_state"] = operation["op"] == "create"
                        observed["matches_proposed_state"] = operation["op"] == "delete"
                        observed["matches_original_identity"] = operation["op"] == "create"
                    elif observed["state"] == "regular_file":
                        observed["matches_original_content"] = (
                            operation["original_sha256"] is not None
                            and observed["sha256"] == operation["original_sha256"]
                        )
                        observed["matches_proposed_content"] = (
                            operation["proposed_sha256"] is not None
                            and observed["sha256"] == operation["proposed_sha256"]
                        )
                        observed["matches_original_identity"] = (
                            operation["original_device"] is not None
                            and observed["device"] == operation["original_device"]
                            and observed["inode"] == operation["original_inode"]
                        )
                        observed["matches_original_state"] = (
                            observed["matches_original_content"]
                            and observed["matches_original_identity"]
                        )
                        observed["matches_proposed_state"] = observed["matches_proposed_content"]
                    observed["matches_known_transaction_state"] = (
                        observed.get("matches_original_state", False)
                        or observed.get("matches_proposed_state", False)
                    )
                    target_states.append(observed)

        return {
            "transaction_id": transaction_id,
            "proposal_id": journal["proposal_id"],
            "proposal_sha256": journal["proposal_sha256"],
            "journal_sha256": journal["journal_sha256"],
            "state": journal["state"],
            "repository_identity_matches": identity_matches,
            "backups": backups,
            "prepared": prepared,
            "missing_backups": missing_backups,
            "missing_prepared": missing_prepared,
            "unexpected_backups": unexpected_backups,
            "unexpected_prepared": unexpected_prepared,
            "unexpected_transaction_entries": unexpected_root_entries,
            "missing_transaction_entries": missing_transaction_entries,
            "targets": target_states,
            "private_artifacts_verified": (
                not missing_backups and not missing_prepared
                and not unexpected_backups and not unexpected_prepared
                and not unexpected_root_entries and not missing_transaction_entries
                and all(item.get("matches_journal", False) for item in backups + prepared)
            ),
        }
    finally:
        os.close(transaction_fd)
