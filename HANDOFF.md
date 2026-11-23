# Handoff

Keep under 300 words. Overwrite each session.

- **Date / environment:** 2026-11-23; Python 3.10+ standard-library implementation.
- **Stable branch:** `main`; PR #14 merged as `4e22a2d4cd414d914cd371990637a8098bca2a53`.
- **Latest completed work:** PRs #1–#14 merged. PR #13 refreshed the handoff and corrected the PR #11 CI record. GitHub ruleset **Protect Main** is active on the default branch: pull requests, required CI checks on Python 3.10–3.13, resolved review conversations, squash-only merges, no force pushes/deletions, no bypass actors.
- **Checks:** PR #13 workflow run [45109477505](https://github.com/hapu/ai-workshop-template/actions/runs/45109477505) passed. Required checks are `checks (3.10)`, `checks (3.11)`, `checks (3.12)`, and `checks (3.13)`.
- **Provider safety:** No live inference was performed. Provider catalog remains empty; do not enable a model until account eligibility, exact quotas, region, external usage, and billing safeguards are verified.
- **Branch audit:** `feature/provider-usage-settlement` is 5 commits behind main with 0 unique commits; no branch deletion was performed.
- **Current work:** `feature/assistant-proposal-intake` implements versioned bounded JSON proposals, path/hash checks, private staging, and read-only previews. CI/review pending.
- **Next:** Verify all CI checks, then harden staged-record integrity and stale-preview detection. Do not implement file application without a separate safety review.
- **Safety:** Never request credentials in chat. Preserve fail-closed quota checks and approval-controlled Git changes.
