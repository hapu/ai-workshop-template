# Handoff

Keep under 300 words. Overwrite each session.

- **Date / environment:** 2026-11-22; Python 3.10+ standard-library implementation.
- **Stable branch:** `main`; latest commit `d0d8720c6c181b195d17a1c9559cef968cac438d` (PR #13).
- **Latest completed work:** PRs #1–#13 merged. PR #13 refreshed the handoff and corrected the PR #11 CI record. GitHub ruleset **Protect Main** is active on the default branch: pull requests, required CI checks on Python 3.10–3.13, resolved review conversations, squash-only merges, no force pushes/deletions, no bypass actors.
- **Checks:** PR #13 workflow run [45109477505](https://github.com/hapu/ai-workshop-template/actions/runs/45109477505) passed. Required checks are `checks (3.10)`, `checks (3.11)`, `checks (3.12)`, and `checks (3.13)`.
- **Provider safety:** No live inference was performed. Provider catalog remains empty; do not enable a model until account eligibility, exact quotas, region, external usage, and billing safeguards are verified.
- **Branch audit:** `feature/provider-usage-settlement` is 5 commits behind main with 0 unique commits; no branch deletion was performed.
- **Current work:** `docs/assistant-proposal-workflow` defines the next Phase 4 milestone: treat browser-assistant outputs as untrusted, reviewable proposals; never execute commands or apply files automatically.
- **Next:** Implement a bounded proposal bundle format, path/hash validation, staging, and a read-only diff preview. Keep apply/commit/push/merge as separate explicit approval steps.
- **Safety:** Never request credentials in chat. Preserve fail-closed quota checks and approval-controlled Git changes.
