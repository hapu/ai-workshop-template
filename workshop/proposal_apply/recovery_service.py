"""Interactive, journal-digest-bound proposal transaction recovery."""
from __future__ import annotations

import os
import re
from typing import TextIO

from .approval import ApprovalError, confirm_recovery_action
from .apply import ApplyError, cleanup_committed_transaction, rollback_transaction
from .filesystem import (
    FilesystemSafetyError,
    _verify_private_directory,
    directory_identity,
    open_private_directory_at,
    open_repository_root,
)
from .journal import JournalError, read_journal
from .locking import LockTimeoutError, transaction_locks
from .recovery import RecoveryInventoryError, inventory_transaction
from ..proposals import ProposalStore


class ProposalRecoveryError(RuntimeError):
    """Raised when a transaction cannot be safely located or recovered."""


_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_PROPOSAL_ID = re.compile(r"^[0-9a-f]{32}$")


def _locate_proposal(proposals_fd: int, transaction_id: str) -> str:
    matches: list[str] = []
    for proposal_id in os.listdir(proposals_fd):
        if not _PROPOSAL_ID.fullmatch(proposal_id):
            continue
        proposal_fd = open_private_directory_at(proposals_fd, proposal_id)
        try:
            try:
                transactions_fd = open_private_directory_at(proposal_fd, "transactions")
            except FilesystemSafetyError:
                continue
            try:
                try:
                    transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
                except FilesystemSafetyError:
                    continue
                try:
                    journal = read_journal(transaction_fd)
                    if journal["transaction_id"] != transaction_id or journal["proposal_id"] != proposal_id:
                        raise ProposalRecoveryError("Transaction directory and journal identities do not match")
                    matches.append(proposal_id)
                except (OSError, JournalError) as exc:
                    raise ProposalRecoveryError(f"Cannot verify transaction journal: {exc}") from exc
                finally:
                    os.close(transaction_fd)
            finally:
                os.close(transactions_fd)
        finally:
            os.close(proposal_fd)
    if len(matches) != 1:
        raise ProposalRecoveryError("Transaction ID was not found uniquely in private proposal state")
    return matches[0]


def _render_inventory(output_stream: TextIO, inventory: dict[str, object]) -> None:
    output_stream.write(f"Transaction: {inventory['transaction_id']}\n")
    output_stream.write(f"State: {inventory['state']}\n")
    output_stream.write(f"Journal SHA-256: {inventory['journal_sha256']}\n")
    output_stream.write(f"Private artifacts verified: {inventory['private_artifacts_verified']}\n")
    targets = inventory.get("targets") or []
    for target in targets:
        output_stream.write(
            f"  TARGET {target.get('state', 'unknown'):18} {target.get('path', '')}"
            f"  sha256={target.get('sha256', '-')}\n"
        )
    siblings = inventory.get("siblings") or []
    for group in siblings:
        for item in group.get("entries", []):
            output_stream.write(
                f"  {item.get('role', 'sibling').upper():9} {item.get('state', 'unknown'):14} "
                f"{group.get('path', '')} :: {item.get('name', '')}"
                f"  verified={item.get('matches_expected', False)}\n"
            )


def _validate_recovery_inventory(inventory: dict[str, object]) -> None:
    state = inventory["state"]
    targets = inventory.get("targets") or []
    siblings = inventory.get("siblings") or []
    if state in {"PREPARING", "PREPARED"}:
        if any(not item.get("matches_original_state", False) for item in targets):
            raise ProposalRecoveryError("Prepared transaction has unexpected target state; refusing cleanup")
        if any(entry.get("state") != "absent" for group in siblings for entry in group.get("entries", [])):
            raise ProposalRecoveryError("Prepared transaction has unexpected repository sibling files")
    elif state in {"APPLYING", "ROLLING_BACK", "NEEDS_RECOVERY"}:
        if any(not item.get("matches_known_transaction_state", False) for item in targets):
            raise ProposalRecoveryError("A target does not match a known transaction state; manual recovery required")
        for group in siblings:
            for entry in group.get("entries", []):
                if entry.get("state") == "absent":
                    continue
                if entry.get("state") != "regular_file" or not entry.get("matches_expected", False):
                    raise ProposalRecoveryError("A transaction sibling is unexpected or unverifiable; manual recovery required")


def recover_proposal_transaction(
    store: ProposalStore,
    transaction_id: str,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    lock_timeout: float = 10.0,
) -> tuple[str, tuple[str, ...]]:
    """Preview and explicitly confirm rollback or committed-transaction cleanup."""
    if not isinstance(transaction_id, str) or not _TRANSACTION_ID.fullmatch(transaction_id):
        raise ProposalRecoveryError("Invalid transaction ID")

    state_fd = proposals_fd = proposal_fd = root_fd = None
    try:
        state_fd = open_repository_root(store.home)
        _verify_private_directory(state_fd)
        proposals_fd = open_private_directory_at(state_fd, "proposals")
        proposal_id = _locate_proposal(proposals_fd, transaction_id)
        proposal_fd = open_private_directory_at(proposals_fd, proposal_id)
        root_fd = open_repository_root(store.repository)

        with transaction_locks(
            state_fd, f"proposal-{proposal_id}.lock", timeout=lock_timeout
        ):
            state2 = proposals2 = proposal2 = root2 = transaction2 = None
            try:
                state2 = open_repository_root(store.home)
                _verify_private_directory(state2)
                proposals2 = open_private_directory_at(state2, "proposals")
                proposal2 = open_private_directory_at(proposals2, proposal_id)
                root2 = open_repository_root(store.repository)
                for before, after, label in (
                    (state_fd, state2, "private state"),
                    (proposal_fd, proposal2, "proposal directory"),
                    (root_fd, root2, "repository root"),
                ):
                    before_id = directory_identity(before)
                    after_id = directory_identity(after)
                    if (before_id.device, before_id.inode) != (after_id.device, after_id.inode):
                        raise ProposalRecoveryError(f"{label} changed while acquiring recovery locks")

                transactions2 = open_private_directory_at(proposal2, "transactions")
                try:
                    transaction2 = open_private_directory_at(transactions2, transaction_id)
                finally:
                    os.close(transactions2)

                journal = read_journal(transaction2)
                if journal["proposal_id"] != proposal_id:
                    raise ProposalRecoveryError("Transaction journal proposal ID does not match its directory")
                inventory = inventory_transaction(
                    proposal2,
                    transaction_id,
                    repository_root_fd=root2,
                    repository_root_path=store.repository,
                )
                if inventory["repository_identity_matches"] is not True:
                    raise ProposalRecoveryError("Repository path or inode identity does not match this transaction")
                _render_inventory(output_stream, inventory)

                if journal["state"] == "ROLLED_BACK":
                    output_stream.write("Already rolled back; no changes made.\n")
                    return "ROLLED_BACK", ()
                if journal["state"] == "COMMITTED":
                    action = "CLEANUP"
                elif journal["state"] in {
                    "PREPARING", "PREPARED", "APPLYING", "ROLLING_BACK", "NEEDS_RECOVERY"
                }:
                    _validate_recovery_inventory(inventory)
                    action = "ROLLBACK"
                else:
                    raise ProposalRecoveryError("Transaction state does not support recovery")

                confirm_recovery_action(
                    action,
                    transaction_id,
                    journal["journal_sha256"],
                    input_stream=input_stream,
                    output_stream=output_stream,
                )
                current = read_journal(transaction2)
                if current["journal_sha256"] != journal["journal_sha256"] or current["state"] != journal["state"]:
                    raise ProposalRecoveryError("Transaction journal changed during interactive recovery review")

                if action == "CLEANUP":
                    warnings = cleanup_committed_transaction(
                        transaction2, root2, repository_root_path=store.repository
                    )
                    output_stream.write("Committed transaction cleanup finished; no rollback was performed.\n")
                    for warning in warnings:
                        output_stream.write(f"Cleanup warning: {warning}\n")
                    return "COMMITTED", warnings

                rolled_back = rollback_transaction(
                    transaction2, root2, repository_root_path=store.repository
                )
                output_stream.write(f"Recovery status: {rolled_back['state']}\n")
                return rolled_back["state"], ()
            except (OSError, FilesystemSafetyError, JournalError, RecoveryInventoryError, ApplyError, ApprovalError, LockTimeoutError) as exc:
                raise ProposalRecoveryError(str(exc)) from exc
            finally:
                for descriptor in (transaction2, root2, proposal2, proposals2, state2):
                    if descriptor is not None:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
    except (OSError, FilesystemSafetyError, LockTimeoutError) as exc:
        raise ProposalRecoveryError(str(exc)) from exc
    finally:
        for descriptor in (root_fd, proposal_fd, proposals_fd, state_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
