"""Journaled proposal application and idempotent rollback primitives."""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from typing import Any, Sequence

from .filesystem import (
    FilesystemSafetyError,
    directory_identity,
    create_sibling_file_at,
    fsync_directory,
    link_file_at,
    open_existing_parent,
    open_private_directory_at,
    open_repository_root,
    read_private_file_at,
    read_regular_file_at,
    unlink_file_at,
)
from .journal import JournalError, read_journal, write_journal
from .transaction import PreparedOperation
from ..proposals import ProposalOperation


class ApplyError(RuntimeError):
    """Raised when proposal application fails or requires manual recovery."""


@dataclass(frozen=True)
class ApplyResult:
    transaction_id: str
    state: str
    cleanup_warnings: tuple[str, ...] = ()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(parent_fd: int, name: str) -> tuple[bytes, os.stat_result] | None:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ApplyError(f"Unexpected non-regular transaction sibling or target: {name}")
    try:
        return read_regular_file_at(parent_fd, name, allow_hardlinks=True)
    except FilesystemSafetyError as exc:
        raise ApplyError(str(exc)) from exc


def _same_identity(info: os.stat_result, device: int | None, inode: int | None) -> bool:
    return device is not None and inode is not None and info.st_dev == device and info.st_ino == inode


def _write_operation(journal: dict[str, Any], index: int, **changes: object) -> dict[str, Any]:
    journal["operations"][index].update(changes)
    return journal


def _verify_private_payload(
    directory_fd: int, filename: str, expected_digest: str, expected_size: int
) -> bytes:
    content = read_private_file_at(directory_fd, filename, max_bytes=65536)
    if len(content) != expected_size or _sha256(content) != expected_digest:
        raise ApplyError(f"Private transaction payload failed integrity check: {filename}")
    return content


def _preflight_targets(
    journal: dict[str, Any],
    repository_root_fd: int,
) -> list[tuple[dict[str, Any], int]]:
    recorded = journal["repository_identity"]
    identity = directory_identity(repository_root_fd)
    if identity.device != recorded["device"] or identity.inode != recorded["inode"]:
        raise ApplyError("Open repository descriptor does not match the transaction identity")

    opened: list[tuple[dict[str, Any], int]] = []
    try:
        for operation in journal["operations"]:
            parts = operation["path"].split("/")
            parent_fd = open_existing_parent(repository_root_fd, parts[:-1])
            target_name = parts[-1]
            try:
                target = _entry(parent_fd, target_name)
                if operation["op"] == "create":
                    if target is not None:
                        raise ApplyError(f"Create destination appeared after staging: {operation['path']}")
                else:
                    if target is None:
                        raise ApplyError(f"Expected original target is missing: {operation['path']}")
                    data, info = target
                    if (info.st_nlink != 1 or _sha256(data) != operation["original_sha256"]
                            or info.st_dev != operation["original_device"]
                            or info.st_ino != operation["original_inode"]
                            or stat.S_IMODE(info.st_mode) != operation["original_mode"]):
                        raise ApplyError(f"Original target changed after staging: {operation['path']}")
                for sibling in (operation["temporary_name"], operation["quarantine_name"]):
                    if sibling is not None and _entry(parent_fd, sibling) is not None:
                        raise ApplyError(f"Unexpected transaction sibling already exists: {sibling}")
                opened.append((operation, parent_fd))
            except BaseException:
                os.close(parent_fd)
                raise
        return opened
    except BaseException:
        for _, descriptor in opened:
            os.close(descriptor)
        raise


def _cleanup_quarantine(
    operation: dict[str, Any], parent_fd: int
) -> str | None:
    name = operation["quarantine_name"]
    if name is None:
        return None
    try:
        entry = _entry(parent_fd, name)
        if entry is None:
            return None
        data, info = entry
        if (_sha256(data) != operation["original_sha256"] or info.st_nlink != 1
                or not _same_identity(info, operation.get("quarantine_device"), operation.get("quarantine_inode"))):
            return f"Refused to remove unexpected quarantine entry: {name}"
        unlink_file_at(parent_fd, name)
        return None
    except (OSError, FilesystemSafetyError, ApplyError) as exc:
        return f"Could not clean quarantine entry {name}: {exc}"


def _mark_needs_recovery(transaction_fd: int, journal: dict[str, Any]) -> None:
    try:
        journal["state"] = "NEEDS_RECOVERY"
        write_journal(transaction_fd, journal)
    except BaseException:
        pass


def rollback_transaction(
    transaction_fd: int,
    repository_root_fd: int,
    *,
    repository_root_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Idempotently restore original target states; preserve unexpected objects."""
    journal = read_journal(transaction_fd)
    if journal["state"] == "COMMITTED":
        raise ApplyError("Committed transactions cannot be rolled back")
    if journal["state"] == "ROLLED_BACK":
        return journal
    if journal["state"] not in {"PREPARING", "PREPARED", "APPLYING", "ROLLING_BACK", "NEEDS_RECOVERY"}:
        raise ApplyError("Transaction state does not permit rollback")
    identity = directory_identity(repository_root_fd)
    recorded = journal["repository_identity"]
    if identity.device != recorded["device"] or identity.inode != recorded["inode"]:
        raise ApplyError("Repository identity does not match the transaction journal")
    if repository_root_path is not None:
        supplied_path = os.path.abspath(os.fspath(repository_root_path))
        if supplied_path != recorded["root"]:
            raise ApplyError("Repository path does not match the transaction journal")
        verified_fd = open_repository_root(supplied_path)
        try:
            verified_identity = directory_identity(verified_fd)
        finally:
            os.close(verified_fd)
        if (verified_identity.device, verified_identity.inode) != (recorded["device"], recorded["inode"]):
            raise ApplyError("Repository path was replaced since transaction preparation")
    if journal["state"] in {"PREPARING", "PREPARED"}:
        journal["state"] = "ROLLED_BACK"
        return write_journal(transaction_fd, journal)

    journal["state"] = "ROLLING_BACK"
    journal = write_journal(transaction_fd, journal)
    try:
        backups_fd = open_private_directory_at(transaction_fd, "backups")
    except FilesystemSafetyError:
        backups_fd = None
    try:
        for index in reversed(range(len(journal["operations"]))):
            operation = journal["operations"][index]
            parts = operation["path"].split("/")
            parent_fd = open_existing_parent(repository_root_fd, parts[:-1])
            target_name = parts[-1]
            temporary_name = operation["temporary_name"]
            quarantine_name = operation["quarantine_name"]
            try:
                target = _entry(parent_fd, target_name)
                temporary = _entry(parent_fd, temporary_name) if temporary_name else None
                quarantine = _entry(parent_fd, quarantine_name) if quarantine_name else None
                proposed_digest = operation["proposed_sha256"]
                original_digest = operation["original_sha256"]

                if operation["op"] == "create":
                    if target is not None:
                        target_data, target_info = target
                        temp_is_same = temporary is not None and (
                            temporary[1].st_dev == target_info.st_dev
                            and temporary[1].st_ino == target_info.st_ino
                            and temporary[1].st_nlink == 2 and target_info.st_nlink == 2
                        )
                        applied_is_same = _same_identity(
                            target_info, operation.get("applied_device"), operation.get("applied_inode")
                        )
                        temp_recorded = temporary is not None and _same_identity(
                            temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                        )
                        if (_sha256(target_data) != proposed_digest
                                or not (temp_is_same and temp_recorded or applied_is_same)):
                            raise ApplyError(f"Cannot prove create target belongs to this transaction: {operation['path']}")
                        unlink_file_at(parent_fd, target_name)
                    if temporary is not None:
                        if (_sha256(temporary[0]) != proposed_digest
                                or not _same_identity(
                                    temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                                )):
                            raise ApplyError(f"Unexpected temporary file during create rollback: {temporary_name}")
                        unlink_file_at(parent_fd, temporary_name)
                    operation["status"] = "DONE"
                    journal = write_journal(transaction_fd, journal)
                    continue

                if quarantine is not None:
                    quarantine_data, quarantine_info = quarantine
                    if (_sha256(quarantine_data) != original_digest
                            or quarantine_info.st_dev != operation["original_device"]
                            or quarantine_info.st_ino != operation["original_inode"]):
                        raise ApplyError(f"Quarantine entry does not match original target: {quarantine_name}")

                if target is not None:
                    target_data, target_info = target
                    original_is_same = (
                        _sha256(target_data) == original_digest
                        and target_info.st_dev == operation["original_device"]
                        and target_info.st_ino == operation["original_inode"]
                    )
                    restored_is_same = (
                        _sha256(target_data) == original_digest
                        and temporary is not None
                        and temporary[1].st_dev == target_info.st_dev
                        and temporary[1].st_ino == target_info.st_ino
                        and temporary[1].st_nlink == 2 and target_info.st_nlink == 2
                        and _same_identity(
                            temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                        )
                    ) or (
                        _sha256(target_data) == original_digest
                        and operation.get("status") == "RESTORED"
                        and _same_identity(
                            target_info, operation.get("applied_device"), operation.get("applied_inode")
                        )
                    )
                    if restored_is_same:
                        if temporary is not None:
                            if not _same_identity(
                                temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                            ):
                                raise ApplyError(f"Unverified rollback temporary: {temporary_name}")
                            unlink_file_at(parent_fd, temporary_name)
                        operation["status"] = "DONE"
                        journal = write_journal(transaction_fd, journal)
                        continue
                    if original_is_same:
                        if quarantine is not None:
                            if ((quarantine_info.st_dev, quarantine_info.st_ino) != (
                                target_info.st_dev, target_info.st_ino
                            ) or quarantine_info.st_nlink != 2 or target_info.st_nlink != 2):
                                raise ApplyError(f"Unexpected quarantine identity: {quarantine_name}")
                            unlink_file_at(parent_fd, quarantine_name)
                        if temporary is not None:
                            expected_temp_digest = proposed_digest if proposed_digest is not None else original_digest
                            if (_sha256(temporary[0]) != expected_temp_digest
                                    or not _same_identity(
                                        temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                                    )):
                                raise ApplyError(f"Unexpected temporary file: {temporary_name}")
                            unlink_file_at(parent_fd, temporary_name)
                        operation["status"] = "DONE"
                        journal = write_journal(transaction_fd, journal)
                        continue

                    applied_is_same = _same_identity(
                        target_info, operation.get("applied_device"), operation.get("applied_inode")
                    )
                    temp_is_same = temporary is not None and (
                        temporary[1].st_dev == target_info.st_dev
                        and temporary[1].st_ino == target_info.st_ino
                        and temporary[1].st_nlink == 2 and target_info.st_nlink == 2
                        and _same_identity(
                            temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                        )
                    )
                    if (operation["op"] == "update" and _sha256(target_data) == proposed_digest
                            and (applied_is_same or temp_is_same)):
                        unlink_file_at(parent_fd, target_name)
                        target = None
                    else:
                        raise ApplyError(f"Unexpected target state during rollback: {operation['path']}")

                if target is None:
                    if quarantine is not None:
                        link_file_at(parent_fd, quarantine_name, target_name)
                        restored = _entry(parent_fd, target_name)
                        quarantine_after = _entry(parent_fd, quarantine_name)
                        if (restored is None or quarantine_after is None or (
                            _sha256(restored[0]) != original_digest
                            or restored[1].st_dev != quarantine_info.st_dev
                            or restored[1].st_ino != quarantine_info.st_ino
                            or restored[1].st_nlink != 2
                            or (quarantine_after[1].st_dev, quarantine_after[1].st_ino) != (
                                restored[1].st_dev, restored[1].st_ino
                            )
                            or quarantine_after[1].st_nlink != 2
                        )):
                            raise ApplyError(f"Could not verify quarantine restoration: {operation['path']}")
                        unlink_file_at(parent_fd, quarantine_name)
                        if temporary is not None:
                            expected_temp_digest = proposed_digest if proposed_digest is not None else original_digest
                            if (_sha256(temporary[0]) != expected_temp_digest
                                    or not _same_identity(
                                        temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                                    )):
                                raise ApplyError(f"Unexpected temporary file: {temporary_name}")
                            unlink_file_at(parent_fd, temporary_name)
                    else:
                        if backups_fd is None:
                            raise ApplyError("Private backup directory is missing; manual recovery is required")
                        backup = _verify_private_payload(
                            backups_fd, operation["backup_file"],
                            original_digest, operation["backup_size"],
                        )
                        if temporary is not None:
                            if not _same_identity(
                                temporary[1], operation.get("temporary_device"), operation.get("temporary_inode")
                            ):
                                raise ApplyError(f"Unverified rollback temporary: {temporary_name}")
                            temporary_digest = _sha256(temporary[0])
                            if temporary_digest != original_digest:
                                if proposed_digest is None or temporary_digest != proposed_digest:
                                    raise ApplyError(f"Temporary file content changed during rollback: {temporary_name}")
                                unlink_file_at(parent_fd, temporary_name)
                                temporary = None
                        if temporary is None:
                            temp_info = create_sibling_file_at(
                                parent_fd, temporary_name, backup, operation["original_mode"]
                            )
                            operation["temporary_device"] = temp_info.st_dev
                            operation["temporary_inode"] = temp_info.st_ino
                            operation["status"] = "RESTORED"
                            journal = write_journal(transaction_fd, journal)
                        link_file_at(parent_fd, temporary_name, target_name)
                        restored = _entry(parent_fd, target_name)
                        temp_now = _entry(parent_fd, temporary_name)
                        if (restored is None or temp_now is None
                                or _sha256(restored[0]) != original_digest
                                or (restored[1].st_dev, restored[1].st_ino) != (
                                    temp_now[1].st_dev, temp_now[1].st_ino
                                ) or restored[1].st_nlink != 2 or temp_now[1].st_nlink != 2):
                            raise ApplyError(f"Could not verify backup restoration: {operation['path']}")
                        operation["applied_device"] = restored[1].st_dev
                        operation["applied_inode"] = restored[1].st_ino
                        operation["status"] = "RESTORED"
                        journal = write_journal(transaction_fd, journal)
                        unlink_file_at(parent_fd, temporary_name)
                operation["status"] = "DONE"
                journal = write_journal(transaction_fd, journal)
            finally:
                os.close(parent_fd)

        journal["state"] = "ROLLED_BACK"
        journal = write_journal(transaction_fd, journal)
        return journal
    except BaseException:
        _mark_needs_recovery(transaction_fd, journal)
        raise
    finally:
        os.close(backups_fd)



def cleanup_committed_transaction(
    transaction_fd: int,
    repository_root_fd: int,
    *,
    repository_root_path: str | os.PathLike[str],
) -> tuple[str, ...]:
    """Remove only verified quarantine links after a durable COMMITTED marker."""
    journal = read_journal(transaction_fd)
    if journal["state"] != "COMMITTED" or journal["version"] != 2:
        raise ApplyError("Only a committed version-two transaction can be cleaned up")
    recorded = journal["repository_identity"]
    identity = directory_identity(repository_root_fd)
    supplied_path = os.path.abspath(os.fspath(repository_root_path))
    if supplied_path != recorded["root"] or (
        identity.device != recorded["device"] or identity.inode != recorded["inode"]
    ):
        raise ApplyError("Repository identity does not match the committed transaction")
    verified_fd = open_repository_root(supplied_path)
    try:
        verified = directory_identity(verified_fd)
    finally:
        os.close(verified_fd)
    if (verified.device, verified.inode) != (recorded["device"], recorded["inode"]):
        raise ApplyError("Repository path was replaced since commit")

    warnings: list[str] = []
    for operation in journal["operations"]:
        parts = operation["path"].split("/")
        parent_fd = open_existing_parent(repository_root_fd, parts[:-1])
        try:
            quarantine_name = operation["quarantine_name"]
            if quarantine_name is not None:
                entry = _entry(parent_fd, quarantine_name)
                if entry is not None:
                    data, info = entry
                    if (_sha256(data) != operation["original_sha256"]
                            or not _same_identity(
                                info, operation.get("quarantine_device"), operation.get("quarantine_inode")
                            )):
                        warnings.append(f"Refused unexpected quarantine entry: {quarantine_name}")
                    else:
                        unlink_file_at(parent_fd, quarantine_name)
            temporary_name = operation["temporary_name"]
            temporary = _entry(parent_fd, temporary_name)
            if temporary is not None:
                warnings.append(f"Unexpected temporary sibling remains after commit: {temporary_name}")
        except (OSError, FilesystemSafetyError, ApplyError) as exc:
            warnings.append(f"Could not clean transaction siblings for {operation['path']}: {exc}")
        finally:
            os.close(parent_fd)
    return tuple(warnings)

def apply_prepared_transaction(
    proposal_dir_fd: int,
    repository_root_fd: int,
    transaction_id: str,
    *,
    proposal_id: str,
    proposal_sha256: str,
    repository_root_path: str | os.PathLike[str],
    operations: Sequence[ProposalOperation],
    snapshots: Sequence[PreparedOperation],
) -> ApplyResult:
    """Apply a PREPARED transaction after interactive approval has succeeded.

    The caller must hold the proposal and repository locks throughout this
    function. Every target change is journaled; failures trigger rollback.
    """
    transactions_fd = open_private_directory_at(proposal_dir_fd, "transactions")
    try:
        transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
    finally:
        os.close(transactions_fd)
    try:
        journal = read_journal(transaction_fd)
        if (journal["version"] != 2 or journal["state"] != "PREPARED"
                or journal["proposal_id"] != proposal_id
                or journal["proposal_sha256"] != proposal_sha256):
            raise ApplyError("Prepared transaction does not match the approved proposal")
        if (len(operations) != len(journal["operations"])
                or len(snapshots) != len(journal["operations"])):
            raise ApplyError("Prepared operation count differs from the approved staged proposal")
        for index, (staged, snapshot, prepared) in enumerate(zip(
            operations, snapshots, journal["operations"]
        ), start=1):
            proposed = staged.content.encode("utf-8") if staged.content is not None else None
            proposed_digest = _sha256(proposed) if proposed is not None else None
            original_digest = _sha256(snapshot.original_content) if snapshot.original_content is not None else None
            prefix = f".workshop-txn-{transaction_id}-{index:04d}"
            expected_quarantine = None if staged.operation == "create" else prefix + ".quarantine"
            if (
                staged.operation != prepared["op"]
                or staged.path != prepared["path"]
                or staged.expected_sha256 != prepared["expected_sha256"]
                or proposed_digest != prepared["proposed_sha256"]
                or snapshot.operation != staged.operation
                or snapshot.path != staged.path
                or snapshot.expected_sha256 != staged.expected_sha256
                or snapshot.proposed_content != proposed
                or original_digest != prepared["original_sha256"]
                or snapshot.original_mode != prepared["original_mode"]
                or snapshot.original_device != prepared["original_device"]
                or snapshot.original_inode != prepared["original_inode"]
                or (len(snapshot.original_content) if snapshot.original_content is not None else None)
                    != prepared["original_size"]
                or (len(proposed) if proposed is not None else None) != prepared["prepared_size"]
                or prepared["backup_file"] != (f"{index:04d}.bin" if snapshot.original_content is not None else None)
                or prepared["prepared_file"] != (f"{index:04d}.bin" if proposed is not None else None)
                or prepared["temporary_name"] != prefix + ".tmp"
                or prepared["quarantine_name"] != expected_quarantine
                or prepared["status"] != "PENDING"
                or any(prepared.get(key) is not None for key in (
                    "applied_device", "applied_inode", "quarantine_device",
                    "quarantine_inode", "temporary_device", "temporary_inode",
                ))
            ):
                raise ApplyError("Prepared journal differs from the approved proposal or live snapshot")
        recorded = journal["repository_identity"]
        identity = directory_identity(repository_root_fd)
        if identity.device != recorded["device"] or identity.inode != recorded["inode"]:
            raise ApplyError("Repository identity changed before application")
        supplied_path = os.path.abspath(os.fspath(repository_root_path))
        if supplied_path != recorded["root"]:
            raise ApplyError("Repository path changed before application")
        verified_fd = open_repository_root(supplied_path)
        try:
            verified_identity = directory_identity(verified_fd)
        finally:
            os.close(verified_fd)
        if (verified_identity.device, verified_identity.inode) != (recorded["device"], recorded["inode"]):
            raise ApplyError("Repository path was replaced before application")

        backups_fd = open_private_directory_at(transaction_fd, "backups")
        try:
            prepared_fd = open_private_directory_at(transaction_fd, "prepared")
        except BaseException:
            os.close(backups_fd)
            raise
        try:
            opened = _preflight_targets(journal, repository_root_fd)
            try:
                for operation in journal["operations"]:
                    if operation["backup_file"] is not None:
                        _verify_private_payload(
                            backups_fd, operation["backup_file"],
                            operation["original_sha256"], operation["backup_size"],
                        )
                    if operation["prepared_file"] is not None:
                        _verify_private_payload(
                            prepared_fd, operation["prepared_file"],
                            operation["proposed_sha256"], operation["prepared_size"],
                        )
                journal["state"] = "APPLYING"
                journal = write_journal(transaction_fd, journal)
                try:
                    for index, (operation, parent_fd) in enumerate(opened):
                        target_name = operation["path"].split("/")[-1]
                        if operation["prepared_file"] is not None:
                            proposed = _verify_private_payload(
                                prepared_fd, operation["prepared_file"],
                                operation["proposed_sha256"], operation["prepared_size"],
                            )
                            mode = operation["original_mode"] if operation["op"] == "update" else 0o644
                            temp_info = create_sibling_file_at(parent_fd, operation["temporary_name"], proposed, mode)
                            operation["temporary_device"] = temp_info.st_dev
                            operation["temporary_inode"] = temp_info.st_ino
                            operation["status"] = "TEMP_READY"
                            journal = write_journal(transaction_fd, journal)

                        if operation["op"] in {"update", "delete"}:
                            link_file_at(parent_fd, target_name, operation["quarantine_name"])
                            quarantine_data, quarantine_info = read_regular_file_at(
                                parent_fd, operation["quarantine_name"], allow_hardlinks=True
                            )
                            if (_sha256(quarantine_data) != operation["original_sha256"]
                                    or quarantine_info.st_dev != operation["original_device"]
                                    or quarantine_info.st_ino != operation["original_inode"]):
                                raise ApplyError(f"Quarantine verification failed: {operation['path']}")
                            operation["quarantine_device"] = quarantine_info.st_dev
                            operation["quarantine_inode"] = quarantine_info.st_ino
                            operation["status"] = "QUARANTINED"
                            journal = write_journal(transaction_fd, journal)

                            target_data, target_info = read_regular_file_at(
                                parent_fd, target_name, allow_hardlinks=True
                            )
                            if (_sha256(target_data) != operation["original_sha256"]
                                    or target_info.st_dev != operation["original_device"]
                                    or target_info.st_ino != operation["original_inode"] or target_info.st_nlink != 2):
                                raise ApplyError(f"Target changed before quarantine removal: {operation['path']}")
                            unlink_file_at(parent_fd, target_name)
                            operation["status"] = "TARGET_REMOVED"
                            journal = write_journal(transaction_fd, journal)

                        if operation["op"] in {"create", "update"}:
                            link_file_at(parent_fd, operation["temporary_name"], target_name)
                            target_data, target_info = read_regular_file_at(
                                parent_fd, target_name, allow_hardlinks=True
                            )
                            temporary_data, temporary_info = read_regular_file_at(
                                parent_fd, operation["temporary_name"], allow_hardlinks=True
                            )
                            if (_sha256(target_data) != operation["proposed_sha256"]
                                    or (target_info.st_dev, target_info.st_ino) != (
                                        temporary_info.st_dev, temporary_info.st_ino
                                    )
                                    or _sha256(temporary_data) != operation["proposed_sha256"]
                                    or target_info.st_nlink != 2 or temporary_info.st_nlink != 2):
                                raise ApplyError(f"Installed target verification failed: {operation['path']}")
                            operation["applied_device"] = target_info.st_dev
                            operation["applied_inode"] = target_info.st_ino
                            operation["status"] = "INSTALLED"
                            journal = write_journal(transaction_fd, journal)
                            unlink_file_at(parent_fd, operation["temporary_name"])
                        operation["status"] = "DONE"
                        journal = write_journal(transaction_fd, journal)

                    for operation, parent_fd in opened:
                        target_name = operation["path"].split("/")[-1]
                        target = _entry(parent_fd, target_name)
                        if operation["op"] == "delete":
                            if target is not None:
                                raise ApplyError(f"Delete target still exists: {operation['path']}")
                        else:
                            if (target is None or _sha256(target[0]) != operation["proposed_sha256"]
                                    or not _same_identity(
                                        target[1], operation["applied_device"], operation["applied_inode"]
                                    )):
                                raise ApplyError(f"Final target verification failed: {operation['path']}")
                    journal["state"] = "COMMITTED"
                    journal = write_journal(transaction_fd, journal)
                except BaseException as exc:
                    try:
                        current = read_journal(transaction_fd)
                    except BaseException as journal_exc:
                        _mark_needs_recovery(transaction_fd, journal)
                        raise ApplyError(
                            f"Application failed and journal cannot be verified: {journal_exc}"
                        ) from exc
                    if current["state"] == "COMMITTED":
                        _mark_needs_recovery(transaction_fd, current)
                        raise ApplyError(
                            "Commit marker exists but final durability could not be confirmed; inspect recovery"
                        ) from exc
                    try:
                        rollback_transaction(transaction_fd, repository_root_fd, repository_root_path=repository_root_path)
                    except BaseException as rollback_exc:
                        _mark_needs_recovery(transaction_fd, current)
                        raise ApplyError(
                            f"Application failed and rollback needs recovery: {rollback_exc}"
                        ) from exc
                    raise ApplyError("Application failed; original files were restored") from exc

                cleanup_warnings: list[str] = []
                for operation, parent_fd in opened:
                    warning = _cleanup_quarantine(operation, parent_fd)
                    if warning:
                        cleanup_warnings.append(warning)
                return ApplyResult(transaction_id, "COMMITTED", tuple(cleanup_warnings))
            finally:
                for _, descriptor in opened:
                    os.close(descriptor)
        finally:
            os.close(backups_fd)
            os.close(prepared_fd)
    finally:
        os.close(transaction_fd)
