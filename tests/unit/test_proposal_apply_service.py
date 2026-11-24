from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from workshop.proposal_apply.service import ProposalApplyServiceError, apply_proposal
from workshop.proposals import ProposalStore


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def proposal_bundle() -> str:
    return json.dumps({
        "format": "ai-workshop-file-proposal",
        "version": 1,
        "source": "service-test",
        "created_at": "2026-11-23T00:00:00Z",
        "operations": [{
            "op": "update",
            "path": "README.md",
            "expected_sha256": sha(b"old readme"),
            "content": "new readme",
        }],
    })


class ProposalApplyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "repo"
        self.root.mkdir()
        (self.root / "README.md").write_bytes(b"old readme")
        self.store = ProposalStore(self.root, base / "state")
        self.staged = self.store.stage(proposal_bundle())
        record = json.loads((self.staged.directory / "proposal.json").read_text(encoding="utf-8"))
        self.digest = record["record_sha256"]
        self.confirmation = f"APPLY {self.staged.proposal_id} {self.digest}\n"

    def test_successful_apply_requires_digest_and_exact_terminal_confirmation(self) -> None:
        output = TTY()
        result = apply_proposal(
            self.store, self.staged.proposal_id, self.digest,
            input_stream=TTY(self.confirmation), output_stream=output,
        )
        self.assertEqual(result.state, "COMMITTED")
        self.assertEqual((self.root / "README.md").read_bytes(), b"new readme")
        self.assertIn(self.digest, output.getvalue())
        self.assertIn("COMMITTED", output.getvalue())

    def test_wrong_digest_fails_before_transaction_creation(self) -> None:
        with self.assertRaisesRegex(ProposalApplyServiceError, "does not match"):
            apply_proposal(
                self.store, self.staged.proposal_id, "f" * 64,
                input_stream=TTY(self.confirmation), output_stream=TTY(),
            )
        transactions = self.staged.directory / "transactions"
        self.assertFalse(transactions.exists())
        self.assertEqual((self.root / "README.md").read_bytes(), b"old readme")

    def test_noninteractive_apply_fails_before_transaction_creation(self) -> None:
        with self.assertRaisesRegex(ProposalApplyServiceError, "interactive terminal"):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=io.StringIO(self.confirmation), output_stream=TTY(),
            )
        self.assertFalse((self.staged.directory / "transactions").exists())
        self.assertEqual((self.root / "README.md").read_bytes(), b"old readme")

    def test_wrong_confirmation_leaves_targets_unchanged(self) -> None:
        with self.assertRaisesRegex(ProposalApplyServiceError, "did not match exactly"):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=TTY("APPLY wrong\n"), output_stream=TTY(),
            )
        self.assertEqual((self.root / "README.md").read_bytes(), b"old readme")
        transactions = self.staged.directory / "transactions"
        self.assertTrue(transactions.is_dir())

    def test_target_change_during_prompt_aborts_before_writes(self) -> None:
        class MutatingInput(TTY):
            def readline(inner_self) -> str:
                (self.root / "README.md").write_bytes(b"external change")
                return self.confirmation

        with self.assertRaisesRegex(ProposalApplyServiceError, "changed during interactive review"):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=MutatingInput(), output_stream=TTY(),
            )
        self.assertEqual((self.root / "README.md").read_bytes(), b"external change")

    def test_record_change_during_prompt_invalidates_approval(self) -> None:
        class MutatingInput(TTY):
            def readline(inner_self) -> str:
                path = self.staged.directory / "proposal.json"
                record = json.loads(path.read_text(encoding="utf-8"))
                record["source"] = "changed during approval"
                path.write_text(json.dumps(record), encoding="utf-8")
                return self.confirmation

        with self.assertRaises(ProposalApplyServiceError):
            apply_proposal(
                self.store, self.staged.proposal_id, self.digest,
                input_stream=MutatingInput(), output_stream=TTY(),
            )
        self.assertEqual((self.root / "README.md").read_bytes(), b"old readme")


if __name__ == "__main__":
    unittest.main()
