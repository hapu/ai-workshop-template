# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main` remains unchanged; proposal-safety work is on the approved design branch and separate review branches.
- **CI:** Stage 1 passed Python 3.10–3.13 (run #83). Stage 2 passed all checks on Python 3.10–3.13 (run #105). Stage 3 CI must be rerun against the latest branch head before review.
- **Implemented:** Standard-library task/checkpoint persistence, bounded context and handoffs, quota ledger/reconciliation, gated OpenRouter adapter, and untrusted proposal import with private staging and read-only preview.
- **Proposal safety design:** Approved. Decisions: POSIX, rollback recovery, existing parent directories only, and interactive digest-bound approval. See `docs/PROPOSAL_APPLICATION_DESIGN.md`.
- **Stage 1 merged:** POSIX filesystem primitives and advisory locks merged by PR #23 into the design branch; squash commit `8f8e4c5`.
- **Stage 2 merged:** Canonical journals, private backups/prepared payloads, lock-held read-only snapshots, and recovery inventory merged by PR #24; squash commit `f006df1`.
- **Stage 3 implemented in draft PR #25:** Version-2 repository-bound staged records, interactive digest approval, recomputed diffs, journaled create/update/delete application, automatic rollback, explicit journal-digest-bound recovery, and CLI `proposal apply/recover`. It is not merged.
- **Next:** Complete stage-4 crash-injection, adversarial path/race, rollback idempotency, and recovery tests; rerun CI on the exact head; review PR #25. Do not merge before stage-4 acceptance.
- **Safety boundary:** No apply/recover command is on `main`. The feature branch does not run shell commands, providers, package managers, or Git write operations.
- **Tomorrow's start:** Check `git status --short --branch`; read this file, `TODO.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`, and the proposal safety design. Continue on the stage-3 feature branch, never directly on `main`.
