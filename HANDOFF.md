# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main` is the source of truth; pull the latest commit before starting.
- **CI:** Main commit passed `checks (3.10)`, `(3.11)`, `(3.12)`, and `(3.13)`. Run `python3 -m unittest discover -s tests/unit -v` and `bash scripts/check-words.sh && bash tests/smoke.sh` locally.
- **Implemented:** Standard-library Python task/checkpoint persistence, bounded context and handoffs, quota ledger/reconciliation, gated OpenRouter adapter, and untrusted proposal import with path/hash validation, private staging, integrity/staleness checks, terminal-safe read-only preview, and optional task/context provenance.
- **Safety:** Provider catalog remains empty. No live inference or paid API use. Proposal import/preview cannot apply files or execute commands. No apply or recovery command exists.
- **Design ready for review:** `docs/PROPOSAL_APPLICATION_DESIGN.md` specifies POSIX-first descriptor-relative filesystem access, proposal/repository advisory locks, exact interactive digest approval, existing parent directories only, durable journaling, and rollback recovery. Decisions are finalized; implementation remains blocked pending review approval.
- **Repository hygiene:** No open PRs. Multiple non-main branches remain; some are stale or diverged after squash merges. No branch deletion was available; inspect before manual cleanup.
- **Next task:** Review and approve the proposal-application safety design. After approval, begin with POSIX filesystem primitives and lock tests only; do not implement application until the design gate is satisfied. Also add manual fallback instructions for exhausted API quotas.
- **Tomorrow's start:** `git switch main && git pull --ff-only`; check `git status --short --branch`; read this file, `TODO.md`, `docs/ROADMAP.md`, and `docs/SECURITY.md`. Start a fresh feature branch; never work directly on `main`.
