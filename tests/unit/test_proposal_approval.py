from __future__ import annotations

import io
import unittest

from workshop.proposal_apply.approval import (
    ApprovalError,
    confirm_interactive,
    verify_approval_digest,
)
from workshop.proposals import ProposalOperation


class TerminalStream(io.StringIO):
    def isatty(self) -> bool:
        return True


class ProposalApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal_id = "a" * 32
        self.digest = "b" * 64
        self.operations = (
            ProposalOperation("update", "README.md", "c" * 64, "new"),
            ProposalOperation("create", "docs/new.md", None, "content"),
        )

    def test_requires_exact_full_digest(self) -> None:
        verify_approval_digest(self.digest, self.digest)
        with self.assertRaises(ApprovalError):
            verify_approval_digest(self.digest, "b" * 63)
        with self.assertRaises(ApprovalError):
            verify_approval_digest(self.digest, "B" * 64)
        with self.assertRaises(ApprovalError):
            verify_approval_digest(self.digest, "c" * 64)

    def test_non_interactive_approval_is_rejected(self) -> None:
        with self.assertRaisesRegex(ApprovalError, "interactive terminal"):
            confirm_interactive(
                self.proposal_id, self.digest, self.operations,
                input_stream=io.StringIO(""), output_stream=io.StringIO(),
            )

    def test_exact_interactive_confirmation_is_accepted(self) -> None:
        expected = f"APPLY {self.proposal_id} {self.digest}\n"
        output = TerminalStream()
        confirm_interactive(
            self.proposal_id, self.digest, self.operations,
            input_stream=TerminalStream(expected), output_stream=output,
        )
        rendered = output.getvalue()
        self.assertIn(self.digest, rendered)
        self.assertIn("UPDATE  README.md", rendered)
        self.assertIn("CREATE  docs/new.md", rendered)

    def test_confirmation_with_extra_space_or_wrong_id_is_rejected(self) -> None:
        for supplied in (
            f"APPLY {self.proposal_id} {self.digest} \n",
            f"APPLY {'d' * 32} {self.digest}\n",
            f"apply {self.proposal_id} {self.digest}\n",
            "",
        ):
            with self.subTest(supplied=supplied), self.assertRaises(ApprovalError):
                confirm_interactive(
                    self.proposal_id, self.digest, self.operations,
                    input_stream=TerminalStream(supplied), output_stream=TerminalStream(),
                )


if __name__ == "__main__":
    unittest.main()
