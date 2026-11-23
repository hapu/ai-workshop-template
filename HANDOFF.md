# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main` is the source of truth; pull the latest commit before starting.
- **CI:** Run #83 passed unit tests, word budgets, and smoke checks on Python 3.10–3.13 for the current stage-1 head `d17d0eb`.
- **Implemented:** Standard-library task/checkpoint persistence, bounded context and handoffs, quota ledger/reconciliation, gated OpenRouter adapter, and untrusted proposal import with private staging and read-only preview.
- **Proposal safety design:** Approved on 2026-11-23. Decisions: POSIX, rollback recovery, existing parent directories only, and interactive digest-bound approval. See `docs/PROPOSAL_APPLICATION_DESIGN.md`.
- **Stage 1 in review:** Draft [PR #23](https://github.com/hapu/ai-workshop-template/pull/23), branch `feat/proposal-apply-posix-primitives`. Adds POSIX capability checks, descriptor-relative no-follow traversal, read-only regular-file inspection, private `flock` locks, and tests. It does not apply proposals, write target files, create journals/backups, or implement recovery.
- **Safety boundary:** Import and preview remain read-only. No apply/recover CLI command exists. Do not begin stage 2 until stage 1 is reviewed.
- **Next task:** Review PR #23 and its full Python 3.10–3.13 CI. After stage 1 is accepted, implement journal format, backup preparation, and recovery inventory only; still no target writes.
- **Other backlog:** Add manual fallback instructions for exhausted API quotas.
- **Tomorrow's start:** Check `git status --short --branch`; read this file, `TODO.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`, and the proposal safety design. Continue on the feature branch, never directly on `main`.
