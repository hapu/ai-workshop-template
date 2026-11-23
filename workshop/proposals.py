"""Validate and stage untrusted browser-assistant file proposals.

Staging is deliberately read-only: this module never modifies repository files,
executes commands, installs packages, or contacts model providers.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_FORMAT = "ai-workshop-file-proposal"
_VERSION = 1
_MAX_BUNDLE_BYTES = 256 * 1024
_MAX_OPERATIONS = 32
_MAX_FILE_BYTES = 64 * 1024
_MAX_PATH_LENGTH = 240
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-f0-9]{32}$")
_SECRET_NAME = re.compile(
    r"(^\.env(?:\.|$)|\.(?:pem|key|p12|pfx)$|"
    r"(?:^|[._-])(credentials?|secrets?|token|api[-_]?key|private-key)(?:[._-]|$))",
    re.IGNORECASE,
)
_PROTECTED_PARTS = {".git", ".workshop", "secrets", "__pycache__", ".ssh", ".aws", ".azure"}


class ProposalError(ValueError):
    """Raised when an untrusted proposal cannot be safely staged."""


@dataclass(frozen=True)
class ProposalOperation:
    operation: str
    path: str
    expected_sha256: str | None
    content: str | None


@dataclass(frozen=True)
class StagedProposal:
    proposal_id: str
    directory: Path
    operations: tuple[ProposalOperation, ...]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(root: Path, raw_path: object) -> tuple[str, Path]:
    if not isinstance(raw_path, str) or not raw_path or len(raw_path) > _MAX_PATH_LENGTH:
        raise ProposalError("Each operation needs a non-empty repository-relative path")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_path):
        raise ProposalError("Paths cannot contain terminal control characters")
    if "\x00" in raw_path or "\\" in raw_path:
        raise ProposalError(f"Invalid path syntax: {raw_path!r}")
    if raw_path.startswith("/") or re.match(r"^[A-Za-z]:", raw_path):
        raise ProposalError("Absolute paths are not allowed")
    parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ProposalError("Paths cannot contain empty, dot, or parent segments")
    if any(part.casefold() in _PROTECTED_PARTS for part in parts):
        raise ProposalError("Proposal targets protected local or Git metadata")
    if any(_SECRET_NAME.search(part) for part in parts):
        raise ProposalError("Proposal targets a credential-like path")
    if raw_path.casefold() == "config/provider-catalog.json":
        raise ProposalError("The local provider catalog is protected")
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or pure.as_posix() != raw_path:
        raise ProposalError("Path is not canonical POSIX repository-relative syntax")

    cursor = root
    for part in parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ProposalError("Symlink path components are not supported")
    if raw_path.casefold() in {".gitignore", ".gitattributes", ".gitmodules"}:
        raise ProposalError("Proposal targets protected repository metadata")
    if raw_path.casefold().startswith(".github/workflows/"):
        raise ProposalError("Proposal targets protected automation workflows")
    target = root.joinpath(*parts)
    # Resolve the parent to detect symlink traversal, including existing links.
    try:
        resolved_parent = target.parent.resolve(strict=False)
        resolved_parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ProposalError("Path escapes the repository through a symlink") from exc
    if target.is_symlink():
        raise ProposalError("Symlink targets are not supported")
    if target.exists() and not target.is_file():
        raise ProposalError("Proposal target exists but is not a regular file")
    return raw_path, target


def parse_proposal(raw: bytes | str) -> tuple[dict[str, Any], tuple[ProposalOperation, ...]]:
    """Parse and structurally validate a bounded version-1 proposal bundle."""
    if isinstance(raw, str):
        try:
            encoded = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProposalError("Proposal is not valid UTF-8") from exc
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        raise ProposalError("Proposal input must be bytes or text")
    if len(encoded) > _MAX_BUNDLE_BYTES:
        raise ProposalError("Proposal exceeds the 256 KiB bundle limit")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProposalError("Proposal must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "format", "version", "source", "created_at", "operations"
    }:
        raise ProposalError("Proposal must contain exactly format, version, source, created_at, operations")
    if payload["format"] != _FORMAT or type(payload["version"]) is not int or payload["version"] != _VERSION:
        raise ProposalError("Unsupported proposal format or version")
    for field in ("source", "created_at"):
        value = payload[field]
        if (not isinstance(value, str) or not value.strip() or len(value) > 200
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ProposalError(f"{field} must be printable text up to 200 characters")
    entries = payload["operations"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= _MAX_OPERATIONS:
        raise ProposalError("Proposal must contain between 1 and 32 file operations")

    operations: list[ProposalOperation] = []
    seen: set[str] = set()
    total_content = 0
    for item in entries:
        if not isinstance(item, dict) or set(item) - {"op", "path", "expected_sha256", "content"}:
            raise ProposalError("Each operation must be an object with supported fields only")
        op = item.get("op")
        if not isinstance(op, str) or op not in {"create", "update", "delete"}:
            raise ProposalError("Supported operations are create, update, and delete")
        path = item.get("path")
        if not isinstance(path, str):
            raise ProposalError("Operation path must be a string")
        folded = path.casefold()
        if folded in seen:
            raise ProposalError("Duplicate proposal paths are not allowed")
        seen.add(folded)
        expected = item.get("expected_sha256")
        content = item.get("content")
        if op == "create":
            if expected is not None:
                raise ProposalError("Create operations must set expected_sha256 to null")
        elif not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise ProposalError("Update and delete operations require a lowercase SHA-256 precondition")
        if op in {"create", "update"}:
            if not isinstance(content, str):
                raise ProposalError("Create and update operations require text content")
            try:
                size = len(content.encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise ProposalError("File content must be valid UTF-8") from exc
            if size > _MAX_FILE_BYTES:
                raise ProposalError("A proposed file exceeds the 64 KiB per-file limit")
            total_content += size
        elif content is not None:
            raise ProposalError("Delete operations must not contain file content")
        if total_content > _MAX_BUNDLE_BYTES:
            raise ProposalError("Combined proposed file content exceeds the bundle limit")
        operations.append(ProposalOperation(op, path, expected, content))
    return payload, tuple(operations)


def _atomic_private_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, temp_name = tempfile.mkstemp(prefix=".proposal-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except OSError:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class ProposalStore:
    """Stage validated proposals privately and render read-only previews."""

    def __init__(self, repository: Path | str, home: Path | str = ".workshop") -> None:
        self.repository = Path(repository).expanduser().resolve()
        if not self.repository.is_dir():
            raise ProposalError("Repository root must be an existing directory")
        self.home = Path(home).expanduser().resolve()
        self.proposals_dir = self.home / "proposals"

    def stage_file(self, bundle: Path | str) -> StagedProposal:
        path = Path(bundle)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ProposalError(f"Cannot read proposal bundle: {exc}") from exc
        return self.stage(raw)

    def stage(self, raw: bytes | str) -> StagedProposal:
        payload, operations = parse_proposal(raw)
        previews: list[dict[str, str]] = []
        for operation in operations:
            _, target = _safe_path(self.repository, operation.path)
            exists = target.exists()
            if operation.operation == "create":
                if exists:
                    raise ProposalError(f"Create target already exists: {operation.path}")
                old = ""
            else:
                if not exists:
                    raise ProposalError(f"Expected existing file is missing: {operation.path}")
                if target.stat().st_size > _MAX_FILE_BYTES:
                    raise ProposalError(f"Existing target exceeds the 64 KiB review limit: {operation.path}")
                current = target.read_bytes()
                if _sha256(current) != operation.expected_sha256:
                    raise ProposalError(f"Stale file hash; proposal rejected: {operation.path}")
                try:
                    old = current.decode("utf-8")
                except UnicodeError as exc:
                    raise ProposalError(f"Existing target is not UTF-8 text: {operation.path}") from exc
            new = operation.content or ""
            if operation.operation == "delete":
                new = ""
            diff = "".join(difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{operation.path}" if exists else "/dev/null",
                tofile=f"b/{operation.path}" if operation.operation != "delete" else "/dev/null",
            ))
            previews.append({"path": operation.path, "operation": operation.operation, "diff": diff})

        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        if self.proposals_dir.is_symlink():
            raise ProposalError("Proposal staging directory must not be a symlink")
        try:
            os.chmod(self.proposals_dir, 0o700)
        except OSError as exc:
            raise ProposalError("Cannot secure the private proposal staging directory") from exc
        proposal_id = uuid.uuid4().hex
        record = {
            "format": _FORMAT,
            "version": _VERSION,
            "proposal_id": proposal_id,
            "source": payload["source"],
            "created_at": payload["created_at"],
            "bundle_sha256": _sha256(_canonical_json(payload)),
            "operations": [
                {"op": op.operation, "path": op.path, "expected_sha256": op.expected_sha256,
                 "content": op.content}
                for op in operations
            ],
            "previews": previews,
            "status": "staged_read_only",
        }
        record["record_sha256"] = _record_digest(record)
        directory = self.proposals_dir / proposal_id
        _atomic_private_write(directory / "proposal.json", _canonical_json(record))
        return StagedProposal(proposal_id, directory, operations)

    def preview(self, proposal_id: str) -> str:
        if not isinstance(proposal_id, str) or not _ID.fullmatch(proposal_id):
            raise ProposalError("Invalid proposal ID")
        directory = self.proposals_dir / proposal_id
        record_path = directory / "proposal.json"
        if self.proposals_dir.is_symlink() or directory.is_symlink() or record_path.is_symlink():
            raise ProposalError("Staged proposal path must not contain symlinks")
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProposalError("Staged proposal not found or unreadable") from exc
        if not isinstance(record, dict) or record.get("format") != _FORMAT:
            raise ProposalError("Staged proposal format is invalid")
        if type(record.get("version")) is not int or record["version"] != _VERSION:
            raise ProposalError("Staged proposal version is invalid")
        if record.get("proposal_id") != proposal_id:
            raise ProposalError("Staged proposal identity does not match its directory")
        supplied_digest = record.get("record_sha256")
        if not isinstance(supplied_digest, str) or not hmac.compare_digest(
            supplied_digest, _record_digest(record)
        ):
            raise ProposalError("Staged proposal integrity check failed; do not review or apply it")

        operations = record.get("operations")
        previews = record.get("previews")
        if (not isinstance(operations, list) or not 1 <= len(operations) <= _MAX_OPERATIONS
                or not isinstance(previews, list) or len(previews) != len(operations)):
            raise ProposalError("Staged proposal contents are malformed")

        stale: list[str] = []
        for item in operations:
            if not isinstance(item, dict):
                raise ProposalError("Staged proposal operation is malformed")
            op, path, expected = item.get("op"), item.get("path"), item.get("expected_sha256")
            _, target = _safe_path(self.repository, path)
            exists = target.exists()
            if op == "create":
                if exists:
                    stale.append(f"{path}: target now exists")
            elif op in {"update", "delete"}:
                if not exists or not target.is_file():
                    stale.append(f"{path}: expected file is now missing")
                else:
                    try:
                        if target.stat().st_size > _MAX_FILE_BYTES:
                            stale.append(f"{path}: current file exceeds the review size limit")
                        elif _sha256(target.read_bytes()) != expected:
                            stale.append(f"{path}: file changed after staging")
                    except OSError as exc:
                        stale.append(f"{path}: cannot verify current file ({exc})")
            else:
                raise ProposalError("Staged proposal contains an unsupported operation")
        if stale:
            details = "; ".join(stale)
            raise ProposalError(f"Staged proposal is stale; discard and restage it: {details}")

        sections = [
            f"Proposal: {proposal_id}",
            f"Source: {_safe_display(str(record.get('source', 'unknown')))}",
            f"Bundle SHA-256: {record.get('bundle_sha256', 'unknown')}",
            f"Record SHA-256: {supplied_digest}",
            "Status: staged_read_only (repository files were not changed)",
            "Freshness: current repository files still match the staged preconditions",
        ]
        for item in previews:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in ("operation", "path", "diff")
            ):
                raise ProposalError("Staged proposal preview is malformed")
            sections.extend([
                "",
                f"## {item['operation']}: {item['path']}",
                _safe_display(item["diff"]) or "(no textual changes)",
            ])
        return "\n".join(sections) + "\n"


def _record_digest(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
    return _sha256(_canonical_json(unsigned))


def _safe_display(value: str) -> str:
    """Escape terminal control characters while preserving ordinary line layout."""
    return "".join(
        char if char in {"\n", "\t"} or ord(char) >= 32 and ord(char) != 127
        else f"\\x{ord(char):02x}"
        for char in value
    )
