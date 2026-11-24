"""Interactive approval bound to the exact staged-record digest."""
from __future__ import annotations

import hmac
import re
from typing import TextIO, Sequence

from .proposals import ProposalOperation

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROPOSAL_ID = re.compile(r"^[0-9a-f]{32}$")


class ApprovalError(ValueError):
    """Raised when interactive proposal approval is missing or invalid."""


def verify_approval_digest(expected_sha256: str, supplied_sha256: str) -> None:
    """Require the complete lowercase staged-record digest."""
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ApprovalError("Staged proposal record digest is invalid")
    if not isinstance(supplied_sha256, str) or not _SHA256.fullmatch(supplied_sha256):
        raise ApprovalError("Supply the full 64-character staged-record SHA-256 digest")
    if not hmac.compare_digest(expected_sha256, supplied_sha256):
        raise ApprovalError("Approval digest does not match the staged proposal record")


def confirm_interactive(
    proposal_id: str,
    record_sha256: str,
    operations: Sequence[ProposalOperation],
    *,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Display operation scope and require one exact terminal confirmation."""
    if not isinstance(proposal_id, str) or not _PROPOSAL_ID.fullmatch(proposal_id):
        raise ApprovalError("Invalid proposal ID")
    if not isinstance(record_sha256, str) or not _SHA256.fullmatch(record_sha256):
        raise ApprovalError("Invalid staged-record SHA-256 digest")
    if not input_stream.isatty() or not output_stream.isatty():
        raise ApprovalError("Proposal application requires an interactive terminal; no files were changed")

    output_stream.write("PROPOSAL APPLICATION REVIEW\n")
    output_stream.write(f"Proposal ID: {proposal_id}\n")
    output_stream.write(f"Staged record SHA-256: {record_sha256}\n")
    output_stream.write(f"Operations: {len(operations)}\n")
    for item in operations:
        output_stream.write(f"  {item.operation.upper():6} {item.path}\n")
    output_stream.write("This action modifies repository files. Type the exact line below to proceed:\n")
    output_stream.write(f"APPLY {proposal_id} {record_sha256}\n> ")
    output_stream.flush()

    line = input_stream.readline()
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    expected = f"APPLY {proposal_id} {record_sha256}"
    if not hmac.compare_digest(line, expected):
        raise ApprovalError("Interactive approval did not match exactly; no repository files were changed")
