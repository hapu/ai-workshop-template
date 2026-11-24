"""Canonical, checksummed transaction journals for proposal safety."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from typing import Any

from .filesystem import read_private_file_at, replace_private_file_at

_FORMAT = "ai-workshop-proposal-transaction"
_VERSION = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_STATES = {
    "PREPARING", "PREPARED", "APPLYING", "COMMITTED",
    "ROLLING_BACK", "ROLLED_BACK", "NEEDS_RECOVERY",
}
_TOP_KEYS = {
    "format", "version", "transaction_id", "proposal_id", "proposal_sha256",
    "repository_identity", "state", "operations", "journal_sha256",
}
_PROTECTED_PARTS = {".git", ".workshop", "secrets", "__pycache__", ".ssh", ".aws", ".azure"}
_SECRET_PART = re.compile(r"(^\.env(?:\.|$)|\.(?:pem|key|p12|pfx)$|(?:^|[._-])(credentials?|secrets?|token|api[-_]?key|private-key)(?:[._-]|$))", re.I)
_OPERATION_KEYS = {
    "index", "op", "path", "expected_sha256", "original_sha256",
    "proposed_sha256", "original_mode", "original_device", "original_inode",
    "original_size", "backup_file", "prepared_file", "backup_size", "prepared_size",
}
_OPERATION_PROGRESS_KEYS = {
    "quarantine_name", "temporary_name", "status", "applied_device",
    "applied_inode", "quarantine_device", "quarantine_inode",
    "temporary_device", "temporary_inode",
}
_PROGRESS_STATES = {"PENDING", "TEMP_READY", "QUARANTINED", "TARGET_REMOVED", "INSTALLED", "RESTORED", "DONE"}


class JournalError(ValueError):
    """Raised when a transaction journal is malformed or fails integrity checks."""


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise JournalError("Journal cannot be represented as canonical UTF-8 JSON") from exc


def _digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "journal_sha256"}
    return hashlib.sha256(canonical_json(unsigned)).hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_optional_nonnegative_int(value: object) -> bool:
    return value is None or (type(value) is int and value >= 0)


def _validate_path(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 240:
        return False
    if value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    parts = value.split("/")
    if not all(part not in {"", ".", ".."} for part in parts):
        return False
    if any(part.casefold() in _PROTECTED_PARTS or _SECRET_PART.search(part) for part in parts):
        return False
    folded = value.casefold()
    return (folded not in {".gitignore", ".gitattributes", ".gitmodules", "config/provider-catalog.json"}
            and not folded.startswith(".github/workflows/"))


def validate_journal(value: object) -> dict[str, Any]:
    """Validate the complete versioned journal schema without trusting its digest."""
    if not isinstance(value, dict) or set(value) != _TOP_KEYS:
        raise JournalError("Journal fields do not match the supported schema")
    if value.get("format") != _FORMAT or type(value.get("version")) is not int or value["version"] not in {1, _VERSION}:
        raise JournalError("Unsupported transaction journal format or version")
    if not isinstance(value.get("transaction_id"), str) or not _TRANSACTION_ID.fullmatch(value["transaction_id"]):
        raise JournalError("Invalid transaction ID in journal")
    if not isinstance(value.get("proposal_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", value["proposal_id"]):
        raise JournalError("Invalid proposal ID in journal")
    if not _is_sha(value.get("proposal_sha256")):
        raise JournalError("Invalid proposal digest in journal")
    if not isinstance(value.get("state"), str) or value["state"] not in _STATES:
        raise JournalError("Unknown transaction state")

    identity = value.get("repository_identity")
    if not isinstance(identity, dict) or set(identity) != {"root", "device", "inode"}:
        raise JournalError("Repository identity is malformed")
    root = identity.get("root")
    if (not isinstance(root, str) or not root.startswith("/") or "\x00" in root
            or os.path.normpath(root) != root):
        raise JournalError("Repository root identity must be a canonical absolute path")
    if identity.get("device") is None or type(identity["device"]) is not int or identity["device"] < 0:
        raise JournalError("Repository device identity is invalid")
    if identity.get("inode") is None or type(identity["inode"]) is not int or identity["inode"] < 0:
        raise JournalError("Repository inode identity is invalid")

    operations = value.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 32:
        raise JournalError("Journal must contain between 1 and 32 operations")
    seen: set[str] = set()
    for expected_index, operation in enumerate(operations, 1):
        expected_operation_keys = _OPERATION_KEYS | (_OPERATION_PROGRESS_KEYS if value["version"] == 2 else set())
        if not isinstance(operation, dict) or set(operation) != expected_operation_keys:
            raise JournalError("Journal operation fields are malformed")
        if type(operation.get("index")) is not int or operation["index"] != expected_index:
            raise JournalError("Journal operation indexes must be sequential")
        if not isinstance(operation.get("op"), str) or operation["op"] not in {"create", "update", "delete"}:
            raise JournalError("Journal operation type is invalid")
        path = operation.get("path")
        if not _validate_path(path) or path.casefold() in seen:
            raise JournalError("Journal operation path is invalid or duplicated")
        seen.add(path.casefold())

        op = operation["op"]
        expected = operation.get("expected_sha256")
        original = operation.get("original_sha256")
        proposed = operation.get("proposed_sha256")
        backup = operation.get("backup_file")
        prepared = operation.get("prepared_file")
        backup_size = operation.get("backup_size")
        prepared_size = operation.get("prepared_size")
        metadata = (
            operation.get("original_mode"), operation.get("original_device"),
            operation.get("original_inode"), operation.get("original_size"),
        )
        if op == "create":
            if (expected is not None or original is not None or any(x is not None for x in metadata)
                    or backup is not None or backup_size is not None):
                raise JournalError("Create operation contains original-file metadata")
            if not _is_sha(proposed) or prepared != f"{expected_index:04d}.bin":
                raise JournalError("Create operation prepared-file metadata is invalid")
            if type(prepared_size) is not int or not 0 <= prepared_size <= 65536:
                raise JournalError("Create operation prepared-file size is invalid")
        elif op == "update":
            if (not _is_sha(expected) or not _is_sha(original) or expected != original
                    or not _is_sha(proposed)):
                raise JournalError("Update operation digest preconditions are invalid")
            if (type(operation.get("original_mode")) is not int
                    or not 0 <= operation["original_mode"] <= 0o777
                    or not _is_optional_nonnegative_int(operation.get("original_device"))
                    or operation.get("original_device") is None
                    or not _is_optional_nonnegative_int(operation.get("original_inode"))
                    or operation.get("original_inode") is None
                    or type(operation.get("original_size")) is not int
                    or not 0 <= operation["original_size"] <= 65536):
                raise JournalError("Update operation original metadata is invalid")
            if backup != f"{expected_index:04d}.bin" or prepared != f"{expected_index:04d}.bin":
                raise JournalError("Update operation private filenames are invalid")
            if type(backup_size) is not int or backup_size != operation["original_size"] or type(prepared_size) is not int or not 0 <= prepared_size <= 65536:
                raise JournalError("Update operation private-file sizes are invalid")
        else:
            if (not _is_sha(expected) or not _is_sha(original) or expected != original
                    or proposed is not None or prepared is not None or prepared_size is not None):
                raise JournalError("Delete operation digest or prepared-file metadata is invalid")
            if (type(operation.get("original_mode")) is not int
                    or not 0 <= operation["original_mode"] <= 0o7777
                    or type(operation.get("original_device")) is not int
                    or operation["original_device"] < 0
                    or type(operation.get("original_inode")) is not int
                    or operation["original_inode"] < 0
                    or type(operation.get("original_size")) is not int
                    or not 0 <= operation["original_size"] <= 65536):
                raise JournalError("Delete operation original metadata is invalid")
            if backup != f"{expected_index:04d}.bin" or type(backup_size) is not int or backup_size != operation["original_size"]:
                raise JournalError("Delete operation backup metadata is invalid")

        if value["version"] == 2:
            quarantine_name = operation.get("quarantine_name")
            temporary_name = operation.get("temporary_name")
            status = operation.get("status")
            if not isinstance(status, str) or status not in _PROGRESS_STATES:
                raise JournalError("Journal operation progress state is invalid")
            prefix = ".workshop-txn-" + value["transaction_id"][:8] + f"-{expected_index:04d}-"
            invalid_chars = lambda name: "/" in name or chr(92) in name or chr(0) in name
            if (not isinstance(temporary_name, str) or not temporary_name.startswith(prefix)
                    or not temporary_name.endswith(".tmp") or invalid_chars(temporary_name)):
                raise JournalError("Journal temporary sibling filename is invalid")
            if op == "create":
                if quarantine_name is not None:
                    raise JournalError("Create operation cannot have a quarantine filename")
            elif (not isinstance(quarantine_name, str) or not quarantine_name.startswith(prefix)
                    or not quarantine_name.endswith(".quarantine") or invalid_chars(quarantine_name)):
                raise JournalError("Journal quarantine sibling filename is invalid")
            if temporary_name == quarantine_name:
                raise JournalError("Journal sibling filenames must be distinct")
            applied_device = operation.get("applied_device")
            applied_inode = operation.get("applied_inode")
            quarantine_device = operation.get("quarantine_device")
            quarantine_inode = operation.get("quarantine_inode")
            temporary_device = operation.get("temporary_device")
            temporary_inode = operation.get("temporary_inode")
            if (not _is_optional_nonnegative_int(applied_device)
                    or not _is_optional_nonnegative_int(applied_inode)
                    or (applied_device is None) != (applied_inode is None)):
                raise JournalError("Applied target identity is invalid")
            if (not _is_optional_nonnegative_int(quarantine_device)
                    or not _is_optional_nonnegative_int(quarantine_inode)
                    or (quarantine_device is None) != (quarantine_inode is None)):
                raise JournalError("Quarantine identity is invalid")
            if op == "create" and (quarantine_device is not None or quarantine_inode is not None):
                raise JournalError("Create operation cannot have a quarantine identity")
            if (not _is_optional_nonnegative_int(temporary_device)
                    or not _is_optional_nonnegative_int(temporary_inode)
                    or (temporary_device is None) != (temporary_inode is None)):
                raise JournalError("Temporary sibling identity is invalid")
    if not _is_sha(value.get("journal_sha256")):
        raise JournalError("Journal integrity digest is missing or malformed")
    return value


def seal_journal(value: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a freshly calculated journal integrity digest."""
    result = dict(value)
    result.pop("journal_sha256", None)
    result["journal_sha256"] = _digest(result)
    validate_journal(result)
    return result


def verify_journal(value: object) -> dict[str, Any]:
    """Validate schema and constant-time compare the canonical journal digest."""
    journal = validate_journal(value)
    if not hmac.compare_digest(journal["journal_sha256"], _digest(journal)):
        raise JournalError("Transaction journal integrity check failed")
    return journal


def write_journal(transaction_dir_fd: int, value: dict[str, Any]) -> dict[str, Any]:
    """Durably replace journal.json and return the sealed journal."""
    sealed = seal_journal(value)
    replace_private_file_at(transaction_dir_fd, "journal.json", canonical_json(sealed))
    return sealed


def read_journal(transaction_dir_fd: int) -> dict[str, Any]:
    """Read canonical JSON from a private descriptor and verify its digest."""
    raw = read_private_file_at(transaction_dir_fd, "journal.json", max_bytes=1024 * 1024)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise JournalError("Transaction journal is not valid UTF-8 JSON") from exc
    journal = verify_journal(value)
    if canonical_json(journal) != raw:
        raise JournalError("Transaction journal is not in canonical JSON form")
    return journal
