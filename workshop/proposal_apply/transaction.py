"""Private backup/prepared-file creation; never modifies repository targets."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import uuid
from dataclasses import dataclass
from typing import Sequence

from .filesystem import (
    FilesystemSafetyError,
    _verify_private_directory,
    create_private_file_at,
    create_private_directory_at,
    directory_identity,
    fsync_directory,
    open_existing_parent,
    open_repository_root,
    open_private_directory_at,
    open_regular_file_at,
)
from .journal import write_journal
from .locking import transaction_locks

_MAX_FILE_BYTES = 64 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROTECTED_PARTS = {".git", ".workshop", "secrets", "__pycache__", ".ssh", ".aws", ".azure"}


class PreparationError(RuntimeError):
    """Raised when safe transaction preparation cannot be completed."""


@dataclass(frozen=True)
class PreparedOperation:
    operation: str
    path: str
    expected_sha256: str | None
    original_content: bytes | None
    proposed_content: bytes | None
    original_mode: int | None = None
    original_device: int | None = None
    original_inode: int | None = None


@dataclass(frozen=True)
class OperationRequest:
    operation: str
    path: str
    expected_sha256: str | None
    proposed_content: bytes | None


@dataclass(frozen=True)
class PreparedTransaction:
    transaction_id: str
    state: str
    journal_sha256: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_path(path: str) -> tuple[str, ...]:
    if (not isinstance(path, str) or not path or len(path) > 240
            or path.startswith("/") or "\\" in path or "\x00" in path):
        raise PreparationError("Operation path must be canonical repository-relative POSIX syntax")
    parts = tuple(path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise PreparationError("Operation path contains an unsafe component")
    if any(part.casefold() in _PROTECTED_PARTS for part in parts):
        raise PreparationError("Operation path targets protected metadata or private state")
    if path.casefold() in {".gitignore", ".gitattributes", ".gitmodules", "config/provider-catalog.json"}:
        raise PreparationError("Operation path targets protected repository configuration")
    if path.casefold().startswith(".github/workflows/"):
        raise PreparationError("Operation path targets protected automation")
    if any(re.search(r"(^\.env(?:\.|$)|\.(?:pem|key|p12|pfx)$|(?:^|[._-])(credentials?|secrets?|token|api[-_]?key|private-key)(?:[._-]|$))", part, re.I) for part in parts):
        raise PreparationError("Operation path looks credential-related")
    return parts


def repository_identity(root_path: str | os.PathLike[str], root_fd: int) -> dict[str, object]:
    """Capture the canonical root path and the identity of its open descriptor."""
    absolute = os.path.abspath(os.fspath(root_path))
    if not isinstance(absolute, str):
        raise PreparationError("Repository root path must be text")
    identity = directory_identity(root_fd)
    verified_fd = open_repository_root(absolute)
    try:
        verified = directory_identity(verified_fd)
    finally:
        os.close(verified_fd)
    if (identity.device, identity.inode) != (verified.device, verified.inode):
        raise PreparationError("Repository path does not identify the supplied root descriptor")
    return {"root": absolute, "device": identity.device, "inode": identity.inode}


def _read_descriptor(descriptor: int) -> tuple[bytes, os.stat_result]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_FILE_BYTES:
        raise PreparationError("Existing target is not a bounded regular file")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(65536, _MAX_FILE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_FILE_BYTES:
            raise PreparationError("Existing target exceeds the 64 KiB preparation limit")
    after = os.fstat(descriptor)
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
        "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink",
    )
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PreparationError("Existing target changed while it was being read")
    content = b"".join(chunks)
    if len(content) != after.st_size:
        raise PreparationError("Existing target size changed while it was being read")
    return content, after


def snapshot_operation(
    repository_root_fd: int,
    operation: str,
    path: str,
    expected_sha256: str | None,
    proposed_content: bytes | None,
) -> PreparedOperation:
    """Read and verify one operation's original bytes through descriptor-relative paths."""
    if not isinstance(operation, str) or operation not in {"create", "update", "delete"}:
        raise PreparationError("Unsupported proposal operation")
    parts = _validate_path(path)
    if operation in {"create", "update"}:
        if not isinstance(proposed_content, bytes) or len(proposed_content) > _MAX_FILE_BYTES:
            raise PreparationError("Create/update content must be bytes up to 64 KiB")
    elif proposed_content is not None:
        raise PreparationError("Delete operation cannot have prepared content")

    try:
        parent_fd = open_existing_parent(repository_root_fd, parts[:-1])
    except FilesystemSafetyError as exc:
        raise PreparationError(str(exc)) from exc
    try:
        if operation == "create":
            if expected_sha256 is not None:
                raise PreparationError("Create operation must not have an expected original digest")
            try:
                os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise PreparationError("Cannot safely inspect create destination") from exc
            else:
                raise PreparationError("Create destination already exists")
            return PreparedOperation(operation, path, None, None, proposed_content)

        if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
            raise PreparationError("Update/delete requires a lowercase SHA-256 precondition")
        descriptor = open_regular_file_at(parent_fd, parts[-1])
        try:
            original, info = _read_descriptor(descriptor)
        finally:
            os.close(descriptor)
        actual = _sha256(original)
        if actual != expected_sha256:
            raise PreparationError("Target no longer matches the proposal's expected SHA-256")
        return PreparedOperation(
            operation, path, expected_sha256, original, proposed_content,
            stat.S_IMODE(info.st_mode), info.st_dev, info.st_ino,
        )
    except FilesystemSafetyError as exc:
        raise PreparationError(str(exc)) from exc
    finally:
        os.close(parent_fd)


def _operation_record(index: int, item: PreparedOperation) -> tuple[dict[str, object], bytes | None, bytes | None]:
    parts = _validate_path(item.path)
    del parts
    if not isinstance(item.operation, str) or item.operation not in {"create", "update", "delete"}:
        raise PreparationError("Unsupported prepared operation")
    original = item.original_content
    proposed = item.proposed_content
    if original is not None and (not isinstance(original, bytes) or len(original) > _MAX_FILE_BYTES):
        raise PreparationError("Original backup exceeds the 64 KiB limit")
    if proposed is not None and (not isinstance(proposed, bytes) or len(proposed) > _MAX_FILE_BYTES):
        raise PreparationError("Prepared content exceeds the 64 KiB limit")

    if item.operation == "create":
        if original is not None or item.expected_sha256 is not None or proposed is None:
            raise PreparationError("Create operation snapshot is inconsistent")
        if any(value is not None for value in (item.original_mode, item.original_device, item.original_inode)):
            raise PreparationError("Create operation must not include original file identity")
    else:
        if original is None or item.expected_sha256 != _sha256(original):
            raise PreparationError("Original bytes do not match the expected digest")
        if (type(item.original_mode) is not int or not 0 <= item.original_mode <= 0o777
                or not item.original_mode & 0o400
                or type(item.original_device) is not int or item.original_device < 0
                or type(item.original_inode) is not int or item.original_inode < 0):
            raise PreparationError("Existing target identity and mode are required")
        if item.operation == "update" and proposed is None:
            raise PreparationError("Update operation requires prepared content")
        if item.operation == "delete" and proposed is not None:
            raise PreparationError("Delete operation cannot include prepared content")

    proposed_digest = _sha256(proposed) if proposed is not None else None
    original_digest = _sha256(original) if original is not None else None
    backup_name = f"{index:04d}.bin" if original is not None else None
    prepared_name = f"{index:04d}.bin" if proposed is not None else None
    record: dict[str, object] = {
        "index": index,
        "op": item.operation,
        "path": item.path,
        "expected_sha256": item.expected_sha256,
        "original_sha256": original_digest,
        "proposed_sha256": proposed_digest,
        "original_mode": item.original_mode,
        "original_device": item.original_device,
        "original_inode": item.original_inode,
        "original_size": len(original) if original is not None else None,
        "backup_file": backup_name,
        "prepared_file": prepared_name,
        "backup_size": len(original) if original is not None else None,
        "prepared_size": len(proposed) if proposed is not None else None,
    }
    return record, original, proposed


def prepare_transaction(
    proposal_dir_fd: int,
    *,
    proposal_id: str,
    proposal_sha256: str,
    repository: dict[str, object],
    repository_root_fd: int,
    operations: Sequence[PreparedOperation],
    transaction_id: str | None = None,
) -> PreparedTransaction:
    """Persist private backups, prepared payloads, and a PREPARED journal.

    This low-level function assumes the caller already holds both transaction
    locks. It writes only below private proposal state and never modifies,
    creates, renames, or deletes repository target paths.
    """
    _verify_private_directory(proposal_dir_fd)
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{32}", proposal_id):
        raise PreparationError("Invalid proposal ID")
    if not isinstance(proposal_sha256, str) or not _SHA256.fullmatch(proposal_sha256):
        raise PreparationError("Invalid proposal digest")
    if (not isinstance(repository, dict) or set(repository) != {"root", "device", "inode"}
            or not isinstance(repository.get("root"), str)
            or not os.path.isabs(repository["root"])
            or type(repository.get("device")) is not int or repository["device"] < 0
            or type(repository.get("inode")) is not int or repository["inode"] < 0):
        raise PreparationError("Repository identity is malformed")
    actual_identity = directory_identity(repository_root_fd)
    verified_root_fd = open_repository_root(repository["root"])
    try:
        path_identity = directory_identity(verified_root_fd)
    finally:
        os.close(verified_root_fd)
    if ((actual_identity.device, actual_identity.inode) != (repository["device"], repository["inode"])
            or (path_identity.device, path_identity.inode) != (repository["device"], repository["inode"])):
        raise PreparationError("Repository path or descriptor does not match the recorded identity")
    if not 1 <= len(operations) <= 32:
        raise PreparationError("Transaction must contain 1 to 32 operations")
    transaction_id = transaction_id or uuid.uuid4().hex
    if not isinstance(transaction_id, str) or not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise PreparationError("Invalid transaction ID")

    records: list[dict[str, object]] = []
    payloads: list[tuple[bytes | None, bytes | None]] = []
    seen: set[str] = set()
    for index, item in enumerate(operations, 1):
        _validate_path(item.path)
        if item.path.casefold() in seen:
            raise PreparationError("Duplicate operation paths are not allowed")
        seen.add(item.path.casefold())
        record, backup, prepared = _operation_record(index, item)
        sibling_prefix = f".workshop-txn-{transaction_id[:8]}-{index:04d}-{uuid.uuid4().hex[:12]}"
        record.update({
            "quarantine_name": None if item.operation == "create" else sibling_prefix + ".quarantine",
            "temporary_name": sibling_prefix + ".tmp",
            "status": "PENDING",
            "applied_device": None,
            "applied_inode": None,
            "quarantine_device": None,
            "quarantine_inode": None,
            "temporary_device": None,
            "temporary_inode": None,
        })
        records.append(record)
        payloads.append((backup, prepared))

    transactions_fd = open_private_directory_at(proposal_dir_fd, "transactions", create=True)
    try:
        transaction_fd = create_private_directory_at(transactions_fd, transaction_id)
    finally:
        os.close(transactions_fd)
    try:
        journal: dict[str, object] = {
            "format": "ai-workshop-proposal-transaction",
            "version": 2,
            "transaction_id": transaction_id,
            "proposal_id": proposal_id,
            "proposal_sha256": proposal_sha256,
            "repository_identity": dict(repository),
            "state": "PREPARING",
            "operations": records,
        }
        write_journal(transaction_fd, journal)
        backups_fd = open_private_directory_at(transaction_fd, "backups", create=True)
        try:
            prepared_fd = open_private_directory_at(transaction_fd, "prepared", create=True)
        except BaseException:
            os.close(backups_fd)
            raise
        try:
            for index, (backup, prepared) in enumerate(payloads, 1):
                filename = f"{index:04d}.bin"
                if backup is not None:
                    create_private_file_at(backups_fd, filename, backup)
                if prepared is not None:
                    create_private_file_at(prepared_fd, filename, prepared)
            fsync_directory(backups_fd)
            fsync_directory(prepared_fd)
            journal["state"] = "PREPARED"
            sealed = write_journal(transaction_fd, journal)
            fsync_directory(transaction_fd)
            return PreparedTransaction(transaction_id, "PREPARED", sealed["journal_sha256"])
        finally:
            os.close(backups_fd)
            os.close(prepared_fd)
    finally:
        os.close(transaction_fd)


def prepare_proposal_transaction(
    state_dir_fd: int,
    proposal_dir_fd: int,
    *,
    repository_path: str | os.PathLike[str],
    repository_root_fd: int,
    proposal_id: str,
    proposal_sha256: str,
    operations: Sequence[OperationRequest],
    timeout: float = 10.0,
    transaction_id: str | None = None,
) -> PreparedTransaction:
    """Acquire both locks, snapshot current targets, and prepare private state.

    The proposal lock is acquired before the repository-wide lock. Both remain
    held until every backup/prepared file and the PREPARED journal are durable.
    Repository target files are opened read-only and are never modified.
    """
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[0-9a-f]{32}", proposal_id):
        raise PreparationError("Invalid proposal ID")
    if not isinstance(proposal_sha256, str) or not _SHA256.fullmatch(proposal_sha256):
        raise PreparationError("Invalid proposal digest")
    if not 1 <= len(operations) <= 32 or any(not isinstance(item, OperationRequest) for item in operations):
        raise PreparationError("Transaction must contain 1 to 32 validated operation requests")
    snapshots: list[PreparedOperation] = []
    with transaction_locks(
        state_dir_fd, f"proposal-{proposal_id}.lock", timeout=timeout
    ):
        identity = repository_identity(repository_path, repository_root_fd)
        for request in operations:
            if not isinstance(request, OperationRequest):
                raise PreparationError("Operations must be validated OperationRequest values")
            snapshots.append(snapshot_operation(
                repository_root_fd,
                request.operation,
                request.path,
                request.expected_sha256,
                request.proposed_content,
            ))
        return prepare_transaction(
            proposal_dir_fd,
            proposal_id=proposal_id,
            proposal_sha256=proposal_sha256,
            repository=identity,
            repository_root_fd=repository_root_fd,
            operations=snapshots,
            transaction_id=transaction_id,
        )
