# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main` remains unchanged; proposal-safety work is on the design branch and review branches.
- **CI:** Stage 1 passed Python 3.10–3.13 (run #83). Stage 2 passed all tests, word budgets, and smoke checks on Python 3.10–3.13 (run #105).
- **Implemented:** Standard-library task/checkpoint persistence, bounded context and handoffs, quota ledger/reconciliation, gated OpenRouter adapter, and untrusted proposal import with private staging and read-only preview.
- **Proposal safety design:** Approved. Decisions: POSIX, rollback recovery, existing parent directories only, and interactive digest-bound approval. See `docs/PROPOSAL_APPLICATION_DESIGN.md`.
- **Stage 1 merged:** POSIX filesystem primitives and advisory locks merged by PR #23; squash commit `8f8e4c5`.
- **Stage 2 merged:** Canonical journals, private backups/prepared payloads, lock-held read-only snapshots, and recovery inventory merged by PR #24; squash commit `f006df1`.
- **Stage 3 next:** Interactive approval, application, verification, rollback, and explicit recovery confirmation. Keep each transaction fail-closed; no shell, provider, package-manager, or Git write operations.
- **Safety boundary:** No apply/recover CLI command exists yet. Import and preview remain read-only. `main` is untouched.
- **Tomorrow's start:** Check `git status --short --branch`; read this file, `TODO.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`, and the proposal safety design. Work on the stage-3 feature branch, never directly on `main`.
