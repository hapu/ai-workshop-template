from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from workshop.proposal_apply.apply import ApplyError
from workshop.proposal_apply.recovery_service import ProposalRecoveryError, recover_proposal_transaction
from workshop.proposal_apply.service import ProposalApplyServiceError, apply_proposal
from workshop.proposals import ProposalStore


class TTY:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        value, self.value = self.value, ""
        return value

    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def proposal_bundle() -> str:
    return json.dumps({
        "format": "ai-workshop-file-proposal",
        "version": 1,
        "source": "crash-test",
        "created_at": "2026-11-23T00:00:00Z",
        "operations": [
            {"op": "update", "path": "docs/note.txt",
             "expected_sha256": sha(b"original note"), "content": "updated note"},
            {"op": "create", "path": "docs/new.txt",
             "expected_sha256": None, "content": "new file"},
            {"op": "delete", "path": "docs/old.txt",
             "expected_sha256": sha(b"remove me")},
        ],
    })


APPLY_CRASH_SCRIPT = textwrap.dedent(r"""
    import os, sys
    from workshop.proposals import ProposalStore
    from workshop.proposal_apply.service import apply_proposal
    from workshop.proposal_apply import apply as apply_module

    root, home, proposal_id, digest, event, operation_filter = sys.argv[1:7]

    class TTYInput:
        def isatty(self): return True
        def readline(self): return f"APPLY {proposal_id} {digest}\n"

    class TTYOutput:
        def isatty(self): return True
        def write(self, value): return sys.stdout.write(value)
        def flush(self): return sys.stdout.flush()

    original = apply_module.write_journal
    def crash_after_durable_write(fd, journal):
        result = original(fd, journal)
        if event.startswith("STATE:") and journal["state"] == event.split(":", 1)[1]:
            os._exit(86)
        if event.startswith("OP:"):
            status = event.split(":", 1)[1]
            if any(op["op"] == operation_filter and op["status"] == status
                   for op in journal["operations"]):
                os._exit(86)
        return result

    apply_module.write_journal = crash_after_durable_write
    store = ProposalStore(root, home)
    apply_proposal(
        store, proposal_id, digest,
        input_stream=TTYInput(), output_stream=TTYOutput(),
    )
""")


RECOVERY_CRASH_SCRIPT = textwrap.dedent(r"""
    import os, sys
    from workshop.proposals import ProposalStore
    from workshop.proposal_apply.recovery_service import recover_proposal_transaction
    from workshop.proposal_apply import apply as apply_module

    root, home, transaction_id, journal_sha, event, operation_filter = sys.argv[1:7]

    class TTYInput:
        def isatty(self): return True
        def readline(self): return f"ROLLBACK {transaction_id} {journal_sha}\n"

    class TTYOutput:
        def isatty(self): return True
        def write(self, value): return sys.stdout.write(value)
        def flush(self): return sys.stdout.flush()

    original = apply_module.write_journal
    def crash_after_durable_write(fd, journal):
        result = original(fd, journal)
        if (event == "ROLLBACK_DONE" and journal["state"] == "ROLLING_BACK"
                and any(op["op"] == operation_filter and op["status"] == "DONE"
                        for op in journal["operations"])):
            os._exit(87)
        return result

    apply_module.write_journal = crash_after_durable_write
    recover_proposal_transaction(
        ProposalStore(root, home), transaction_id,
        input_stream=TTYInput(), output_stream=TTYOutput(),
    )
""")


class ProposalCrashRecoveryTests(unittest.TestCase):
    def _case(self, base: Path):
        root = base / "repo"
        (root / "docs").mkdir(parents=True)
        (root / "docs/note.txt").write_bytes(b"original note")
        (root / "docs/old.txt").write_bytes(b"remove me")
        home = base / "state"
        store = ProposalStore(root, home)
        staged = store.stage(proposal_bundle())
        record = json.loads((staged.directory / "proposal.json").read_text(encoding="utf-8"))
        return root, home, store, staged, record["record_sha256"]

    def _run_apply_crash(self, root: Path, home: Path, proposal_id: str, digest: str,
                         event: str, operation: str = "-") -> tuple[str, str]:
        result = subprocess.run(
            [sys.executable, "-c", APPLY_CRASH_SCRIPT, str(root), str(home),
             proposal_id, digest, event, operation],
            cwd=Path.cwd(), capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 86, msg=result.stdout + result.stderr)
        marker = "Prepared transaction ID: "
        transaction_id = next(
            line.split(marker, 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith(marker)
        )
        return transaction_id, result.stdout

    def _read_journal(self, staged_dir: Path, transaction_id: str) -> dict:
        path = staged_dir / "transactions" / transaction_id / "journal.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _recover(self, store: ProposalStore, transaction_id: str, journal: dict):
        action = "CLEANUP" if journal["state"] == "COMMITTED" else "ROLLBACK"
        confirmation = f"{action} {transaction_id} {journal['journal_sha256']}\n"
        return recover_proposal_transaction(
            store, transaction_id,
            input_stream=TTY(confirmation), output_stream=TTY(),
        )

    def test_crashes_at_apply_boundaries_roll_back_to_original_state(self) -> None:
        cases = [
            ("STATE:APPLYING", "-"),
            ("OP:QUARANTINED", "update"),
            ("OP:TARGET_REMOVED", "update"),
            ("OP:INSTALLED", "update"),
            ("OP:DONE", "update"),
            ("OP:INSTALLED", "create"),
            ("OP:TARGET_REMOVED", "delete"),
        ]
        for event, operation in cases:
            with self.subTest(event=event, operation=operation), tempfile.TemporaryDirectory() as temp:
                root, home, store, staged, digest = self._case(Path(temp))
                transaction_id, _ = self._run_apply_crash(
                    root, home, staged.proposal_id, digest, event, operation
                )
                journal = self._read_journal(staged.directory, transaction_id)
                self.assertEqual(journal["state"], "APPLYING")
                state, _ = self._recover(store, transaction_id, journal)
                self.assertEqual(state, "ROLLED_BACK")
                self.assertEqual((root / "docs/note.txt").read_bytes(), b"original note")
                self.assertEqual((root / "docs/old.txt").read_bytes(), b"remove me")
                self.assertFalse((root / "docs/new.txt").exists())

    def test_crash_after_commit_marker_performs_cleanup_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, home, store, staged, digest = self._case(Path(temp))
            transaction_id, _ = self._run_apply_crash(
                root, home, staged.proposal_id, digest, "STATE:COMMITTED"
            )
            journal = self._read_journal(staged.directory, transaction_id)
            self.assertEqual(journal["state"], "COMMITTED")
            state, warnings = self._recover(store, transaction_id, journal)
            self.assertEqual(state, "COMMITTED")
            self.assertEqual(warnings, ())
            self.assertEqual((root / "docs/note.txt").read_bytes(), b"updated note")
            self.assertEqual((root / "docs/new.txt").read_bytes(), b"new file")
            self.assertFalse((root / "docs/old.txt").exists())

    def test_recovery_itself_can_be_interrupted_and_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, home, store, staged, digest = self._case(Path(temp))
            transaction_id, _ = self._run_apply_crash(
                root, home, staged.proposal_id, digest, "OP:TARGET_REMOVED", "update"
            )
            journal = self._read_journal(staged.directory, transaction_id)
            crash = subprocess.run(
                [sys.executable, "-c", RECOVERY_CRASH_SCRIPT, str(root), str(home),
                 transaction_id, journal["journal_sha256"], "ROLLBACK_DONE", "delete"],
                cwd=Path.cwd(), capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(crash.returncode, 87, msg=crash.stdout + crash.stderr)
            interrupted = self._read_journal(staged.directory, transaction_id)
            self.assertEqual(interrupted["state"], "ROLLING_BACK")
            state, _ = self._recover(store, transaction_id, interrupted)
            self.assertEqual(state, "ROLLED_BACK")
            self.assertEqual((root / "docs/note.txt").read_bytes(), b"original note")
            self.assertEqual((root / "docs/old.txt").read_bytes(), b"remove me")
            self.assertFalse((root / "docs/new.txt").exists())

    def test_symlink_swap_during_quarantine_is_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, home, store, staged, digest = self._case(Path(temp))
            external = Path(temp) / "outside-secret.txt"
            external.write_text("do not read or modify", encoding="utf-8")
            from workshop.proposal_apply import apply as apply_module
            original_link = apply_module.link_file_at

            def swap_to_symlink(parent_fd: int, source: str, destination: str) -> None:
                if source == "note.txt" and destination.endswith(".quarantine"):
                    os.unlink(source, dir_fd=parent_fd)
                    os.symlink(str(external), source, dir_fd=parent_fd)
                original_link(parent_fd, source, destination)

            output = TTY()
            with patch("workshop.proposal_apply.apply.link_file_at", side_effect=swap_to_symlink):
                with self.assertRaises(ProposalApplyServiceError):
                    apply_proposal(
                        store, staged.proposal_id, digest,
                        input_stream=TTY(f"APPLY {staged.proposal_id} {digest}\n"),
                        output_stream=output,
                    )
            self.assertTrue((root / "docs/note.txt").is_symlink())
            self.assertEqual(external.read_text(encoding="utf-8"), "do not read or modify")

    def test_extra_hardlink_during_quarantine_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, home, store, staged, digest = self._case(Path(temp))
            from workshop.proposal_apply import apply as apply_module
            original_link = apply_module.link_file_at

            def add_external_link(parent_fd: int, source: str, destination: str) -> None:
                original_link(parent_fd, source, destination)
                if destination.endswith(".quarantine"):
                    os.link(
                        destination, "external-hardlink",
                        src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False,
                    )

            output = TTY()
            with patch("workshop.proposal_apply.apply.link_file_at", side_effect=add_external_link):
                with self.assertRaises(ProposalApplyServiceError):
                    apply_proposal(
                        store, staged.proposal_id, digest,
                        input_stream=TTY(f"APPLY {staged.proposal_id} {digest}\n"),
                        output_stream=output,
                    )
            transaction_id = next(
                line.split("Prepared transaction ID: ", 1)[1]
                for line in output.getvalue().splitlines()
                if line.startswith("Prepared transaction ID: ")
            )
            journal = self._read_journal(staged.directory, transaction_id)
            self.assertEqual(journal["state"], "NEEDS_RECOVERY")
            self.assertEqual((root / "docs/note.txt").read_bytes(), b"original note")
            self.assertEqual((root / "docs/external-hardlink").read_bytes(), b"original note")
            with self.assertRaises(ProposalRecoveryError):
                self._recover(store, transaction_id, journal)


if __name__ == "__main__":
    unittest.main()
