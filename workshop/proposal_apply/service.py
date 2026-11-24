"""Approval-gated proposal application service."""
from __future__ import annotations

import os
import re
from typing import TextIO

from .approval import confirm_interactive, verify_approval_digest
from .apply import ApplyError, ApplyResult, apply_prepared_transaction
from .filesystem import (
    FilesystemSafetyError,
    directory_identity,
    open_private_directory_at,
)
from .journal import JournalError, read_journal
from .locking import transaction_locks
from .transaction import (
    PreparationError,
    prepare_transaction,
    repository_identity,
    snapshot_operation,
)
from ..proposals import ProposalError, ProposalStore, _safe_display


class ProposalApplyServiceError(RuntimeError):
    """Raised when an approved proposal cannot safely be prepared or applied."""


def _close_all(descriptors: tuple[int | None, ...]) -> None:
    for descriptor in descriptors:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _ensure_no_unresolved_transaction(proposal_dir_fd: int, proposal_id: str) -> None:
    try:
        os.stat("transactions", dir_fd=proposal_dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    transactions_fd = open_private_directory_at(proposal_dir_fd, "transactions")
    try:
        for transaction_id in os.listdir(transactions_fd):
            if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
                raise ProposalApplyServiceError("Unexpected entry in private transaction directory")
            transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
            try:
                try:
                    journal = read_journal(transaction_fd)
                except (OSError, FilesystemSafetyError, JournalError) as exc:
                    raise ProposalApplyServiceError(
                        f"Unverifiable previous transaction blocks application: {transaction_id}"
                    ) from exc
                if journal["proposal_id"] != proposal_id:
                    raise ProposalApplyServiceError("Transaction proposal identity does not match its directory")
                if journal["state"] == "COMMITTED":
                    raise ProposalApplyServiceError("This proposal has already been committed; it cannot be replayed")
                if journal["state"] != "ROLLED_BACK":
                    raise ProposalApplyServiceError(
                        f"Previous transaction {transaction_id} is {journal['state']}; run recovery first"
                    )
            finally:
                os.close(transaction_fd)
    finally:
        os.close(transactions_fd)


def apply_proposal(
    store: ProposalStore,
    proposal_id: str,
    supplied_record_sha256: str,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    lock_timeout: float = 10.0,
) -> ApplyResult:
    """Verify staged record, prepare, obtain exact terminal approval, then apply."""
    initial_state_fd = initial_proposal_fd = initial_root_fd = None
    try:
        initial_state_fd, initial_proposal_fd, initial_root_fd, _, _ = store.open_for_apply(proposal_id)
        with transaction_locks(
            initial_state_fd, f"proposal-{proposal_id}.lock", timeout=lock_timeout
        ):
            state_fd, proposal_dir_fd, repository_root_fd, record, operations = store.open_for_apply(proposal_id)
            try:
                for before, after, label in (
                    (initial_state_fd, state_fd, "private state"),
                    (initial_proposal_fd, proposal_dir_fd, "proposal directory"),
                    (initial_root_fd, repository_root_fd, "repository root"),
                ):
                    before_id = directory_identity(before)
                    after_id = directory_identity(after)
                    if (before_id.device, before_id.inode) != (after_id.device, after_id.inode):
                        raise ProposalApplyServiceError(f"{label} changed while acquiring the transaction lock")

                verify_approval_digest(record["record_sha256"], supplied_record_sha256)
                _ensure_no_unresolved_transaction(proposal_dir_fd, proposal_id)
                identity = repository_identity(store.repository, repository_root_fd)
                snapshots = []
                for operation in operations:
                    proposed = operation.content.encode("utf-8") if operation.content is not None else None
                    snapshots.append(snapshot_operation(
                        repository_root_fd,
                        operation.operation,
                        operation.path,
                        operation.expected_sha256,
                        proposed,
                    ))

                prepared = prepare_transaction(
                    proposal_dir_fd,
                    proposal_id=proposal_id,
                    proposal_sha256=record["record_sha256"],
                    repository=identity,
                    repository_root_fd=repository_root_fd,
                    operations=snapshots,
                )

                output_stream.write("Staged proposal preview:\n")
                for preview in record["previews"]:
                    output_stream.write(f"\n## {preview['operation']}: {preview['path']}\n")
                    output_stream.write(_safe_display(preview["diff"]) or "(no textual changes)")
                    if not preview["diff"].endswith("\n"):
                        output_stream.write("\n")
                confirm_interactive(
                    proposal_id,
                    record["record_sha256"],
                    operations,
                    input_stream=input_stream,
                    output_stream=output_stream,
                )

                for operation, snapshot in zip(operations, snapshots):
                    proposed = operation.content.encode("utf-8") if operation.content is not None else None
                    current = snapshot_operation(
                        repository_root_fd,
                        operation.operation,
                        operation.path,
                        operation.expected_sha256,
                        proposed,
                    )
                    if current != snapshot:
                        raise ProposalApplyServiceError(
                            f"Target changed during interactive review: {operation.path}; no files were applied"
                        )

                result = apply_prepared_transaction(
                    proposal_dir_fd,
                    repository_root_fd,
                    prepared.transaction_id,
                    proposal_id=proposal_id,
                    proposal_sha256=record["record_sha256"],
                    operations=operations,
                )
                output_stream.write(f"\nTransaction: {result.transaction_id}\n")
                output_stream.write(f"Status: {result.state}\n")
                for warning in result.cleanup_warnings:
                    output_stream.write(f"Cleanup warning: {warning}\n")
                return result
            finally:
                _close_all((state_fd, proposal_dir_fd, repository_root_fd))
    except (ProposalError, PreparationError, ApplyError, FilesystemSafetyError) as exc:
        raise ProposalApplyServiceError(str(exc)) from exc
    finally:
        _close_all((initial_state_fd, initial_proposal_fd, initial_root_fd))
