# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main` remains unchanged; all proposal-safety work is on the design branch and review branches.
- **CI:** Stage 1 passed unit tests, word budgets, and smoke checks on Python 3.10–3.13 (run #83). Stage 2 CI is running for PR #24.
- **Implemented:** Standard-library task/checkpoint persistence, bounded context and handoffs, quota ledger/reconciliation, gated OpenRouter adapter, and untrusted proposal import with private staging and read-only preview.
- **Proposal safety design:** Approved. Decisions: POSIX, rollback recovery, existing parent directories only, and interactive digest-bound approval. See `docs/PROPOSAL_APPLICATION_DESIGN.md`.
- **Stage 1 merged:** POSIX filesystem primitives and advisory locks merged into `docs/proposal-application-safety-design` by squash commit `8f8e4c5`. PR #23 is merged; `main` was not changed.
- **Stage 2 under review:** Draft [PR #24](https://github.com/hapu/ai-workshop-template/pull/24), branch `feat/proposal-apply-journal-preparation`. Adds canonical journals, private backups/prepared files, read-only target snapshots, and recovery inventory. It never modifies repository targets.
- **Safety boundary:** No approval, apply, rollback, recovery action, or CLI command exists. Import and preview remain read-only.
- **Next task:** Review PR #24 and require passing CI on Python 3.10–3.13. Only after stage 2 is accepted should stage 3 implement interactive approval, apply, and rollback.
- **Tomorrow's start:** Check `git status --short --branch`; read this file, `TODO.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`, and the proposal safety design. Continue on the review branch, never directly on `main`.
