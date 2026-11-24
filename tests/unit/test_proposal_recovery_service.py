from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workshop.proposal_apply.apply import ApplyError, apply_prepared_transaction
from workshop.proposal_apply.locking import transaction_locks
from workshop.proposal_apply.recovery_service import (
    ProposalRecoveryError,
    recover_proposal_transaction,
)
from workshop.proposal_apply.journal import read_journal
from workshop.proposal_apply.filesystem import open_private_directory_at
from workshop.proposal_apply.service import ProposalApplyServiceError, apply_proposal
from workshop.proposals import ProposalStore


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle() -> str:
    return json.dumps({
        "format": "ai-workshop-file-proposal",
        "version": 1,
        "source": "recovery-test",
        "created_at": "2026-11-23T00:00:00Z",
        "operations": [{
            "op": "update",
            "path": "README.md",
            "expected_sha256": sha(b"original"),
            "content": "updated",
        }],
    })


class ProposalRecoveryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        (self.root / "README.md").write_bytes(b"original")
        self.store = ProposalStore(self.root, base / "state")
        self.staged = self.store.stage(bundle())
        record = json.loads((self.staged.directory / "proposal.json").read_text(encoding="utf-8"))
        self.digest = record["record_sha256"]

    def _journal(self, transaction_id: str) -> dict:
        state_fd, proposal_fd, root_fd, _, _ = self.store.open_for_apply(self.staged.proposal_id)
        try:
            transactions_fd = open_private_directory_at(proposal_fd, "transactions")
            try:
                transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
            finally:
                os.close(transactions_fd)
            try:
                return read_journal(transaction_fd)
            finally:
                os.close(transaction_fd)
        finally:
            for descriptor in (root_fd, proposal_fd, state_fd):
                os.close(descriptor)

    def test_prepared_transaction_can_be_explicitly_rolled_back(self) -> None:
        output = TTY()
        with self.assertRaises(ProposalApplyServiceError):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=TTY("wrong\n"), output_stream=output,
            )
        marker = "Prepared transaction ID: "
        transaction_id = next(
            line.split(marker, 1)[1]
            for line in output.getvalue().splitlines()
            if line.startswith(marker)
        )
        journal = self._journal(transaction_id)
        confirmation = f"ROLLBACK {transaction_id} {journal['journal_sha256']}\n"
        state, warnings = recover_proposal_transaction(
            self.store, transaction_id,
            input_stream=TTY(confirmation), output_stream=TTY(),
        )
        self.assertEqual(state, "ROLLED_BACK")
        self.assertEqual(warnings, ())
        self.assertEqual((self.root / "README.md").read_bytes(), b"original")

    def test_recovery_requires_exact_confirmation(self) -> None:
        output = TTY()
        with self.assertRaises(ProposalApplyServiceError):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=TTY("wrong\n"), output_stream=output,
            )
        marker = "Prepared transaction ID: "
        transaction_id = next(
            line.split(marker, 1)[1]
            for line in output.getvalue().splitlines()
            if line.startswith(marker)
        )
        with self.assertRaisesRegex(ProposalRecoveryError, "did not match exactly"):
            recover_proposal_transaction(
                self.store, transaction_id,
                input_stream=TTY("ROLLBACK wrong\n"), output_stream=TTY(),
            )
        self.assertEqual((self.root / "README.md").read_bytes(), b"original")
        self.assertEqual(self._journal(transaction_id)["state"], "PREPARED")

    def test_recovery_rolls_back_interrupted_apply(self) -> None:
        output = TTY()
        with self.assertRaises(ProposalApplyServiceError):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=TTY("wrong\n"), output_stream=output,
            )
        marker = "Prepared transaction ID: "
        transaction_id = next(
            line.split(marker, 1)[1]
            for line in output.getvalue().splitlines()
            if line.startswith(marker)
        )
        state_fd, proposal_fd, root_fd, record, operations = self.store.open_for_apply(self.staged.proposal_id)
        try:
            with transaction_locks(state_fd, f"proposal-{self.staged.proposal_id}.lock"):
                transactions_fd = open_private_directory_at(proposal_fd, "transactions")
                try:
                    transaction_fd = open_private_directory_at(transactions_fd, transaction_id)
                finally:
                    os.close(transactions_fd)
                try:
                    journal = read_journal(transaction_fd)
                    journal["state"] = "APPLYING"
                    from workshop.proposal_apply.journal import write_journal
                    write_journal(transaction_fd, journal)
                finally:
                    os.close(transaction_fd)
        finally:
            for descriptor in (root_fd, proposal_fd, state_fd):
                os.close(descriptor)

        # This is a simulated process interruption after the durable APPLYING marker
        # but before any target mutation. Recovery must safely return to the original state.
        journal = self._journal(transaction_id)
        confirmation = f"ROLLBACK {transaction_id} {journal['journal_sha256']}\n"
        state, _ = recover_proposal_transaction(
            self.store, transaction_id,
            input_stream=TTY(confirmation), output_stream=TTY(),
        )
        self.assertEqual(state, "ROLLED_BACK")
        self.assertEqual((self.root / "README.md").read_bytes(), b"original")

    def test_recovery_restores_target_after_interrupted_quarantine_install(self) -> None:
        from workshop.proposal_apply import apply as apply_module

        original_link = apply_module.link_file_at

        def fail_install(parent_fd: int, source: str, destination: str) -> None:
            if destination == "README.md":
                raise OSError("simulated crash after original target was quarantined")
            original_link(parent_fd, source, destination)

        output = TTY()
        with patch("workshop.proposal_apply.apply.link_file_at", side_effect=fail_install):
            with patch(
                "workshop.proposal_apply.apply.rollback_transaction",
                side_effect=ApplyError("simulated rollback interruption"),
            ):
                with self.assertRaises(ProposalApplyServiceError):
                    apply_proposal(
                        self.store, self.staged.proposal_id, self.digest,
                        input_stream=TTY(f"APPLY {self.staged.proposal_id} {self.digest}\n"),
                        output_stream=output,
                    )
        marker = "Prepared transaction ID: "
        transaction_id = next(
            line.split(marker, 1)[1]
            for line in output.getvalue().splitlines()
            if line.startswith(marker)
        )
        journal = self._journal(transaction_id)
        self.assertEqual(journal["state"], "NEEDS_RECOVERY")
        self.assertFalse((self.root / "README.md").exists())

        confirmation = f"ROLLBACK {transaction_id} {journal['journal_sha256']}\n"
        state, _ = recover_proposal_transaction(
            self.store, transaction_id,
            input_stream=TTY(confirmation), output_stream=TTY(),
        )
        self.assertEqual(state, "ROLLED_BACK")
        self.assertEqual((self.root / "README.md").read_bytes(), b"original")

    def test_committed_recovery_is_cleanup_only(self) -> None:
        # A successful apply normally cleans quarantine entries. The cleanup
        # path is tested by invoking recovery on the already committed journal.
        output = TTY()
        result = apply_proposal(
            self.store, self.staged.proposal_id, self.digest,
            input_stream=TTY(f"APPLY {self.staged.proposal_id} {self.digest}\n"),
            output_stream=output,
        )
        journal = self._journal(result.transaction_id)
        confirmation = f"CLEANUP {result.transaction_id} {journal['journal_sha256']}\n"
        state, _ = recover_proposal_transaction(
            self.store, result.transaction_id,
            input_stream=TTY(confirmation), output_stream=TTY(),
        )
        self.assertEqual(state, "COMMITTED")
        self.assertEqual((self.root / "README.md").read_bytes(), b"updated")


if __name__ == "__main__":
    unittest.main()
