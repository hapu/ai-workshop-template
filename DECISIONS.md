# Decisions

One entry per important decision, newest first. Supersede decisions instead of deleting them.

## 2026-11-21: Start with a standard-library task CLI
- **Status:** accepted
- **Decision:** Use Python 3.10+ and JSON files for the first executable task-management slice. Keep model providers, browser integrations, and Git automation out of this phase.
- **Why:** This is lightweight, testable on the target Chromebook, requires no paid service, and creates a stable task/handoff boundary for later components.
- **Alternatives rejected:** A database, web UI, local model runtime, and multi-agent orchestration in the first iteration.
- **Consequences / follow-up:** Add provider and workflow modules only behind tested interfaces; keep `.workshop/` private and untracked.

## 2026-11-21: Preserve the existing GPL-3.0 license
- **Status:** accepted
- **Decision:** Keep the repository's existing GPL-3.0 `LICENSE` and correct README references to match it.
- **Why:** The license file and GitHub repository metadata both identify GPL-3.0; there was no instruction to relicense the repository.
- **Alternatives rejected:** Replacing the license with Apache-2.0 without an explicit licensing decision.
- **Consequences / follow-up:** Ensure future documentation and template metadata consistently identify GPL-3.0.

## YYYY-MM-DD: Title
- **Status:** proposed / accepted / superseded
- **Decision:**
- **Why:**
- **Alternatives rejected:**
- **Consequences / follow-up:**
