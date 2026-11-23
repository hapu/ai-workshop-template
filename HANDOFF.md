# Handoff

Keep under 300 words. Overwrite each session.

- **Date / environment:** 2026-11-23; Python 3.10+ standard-library implementation.
- **Stable branch:** `main`; PR #20 merged as `cb81a6e458b3cc06d95af9abd9985d6aad42a0fe`.
- **Latest completed work:** PRs #1–#20 merged. PR #19 was closed unmerged after a documentation word-budget correction; PR #20 contains the verified change. PR #15 was closed unmerged after a test assertion correction; PR #16 contains the verified proposal intake. PR #13 refreshed the handoff and corrected the PR #11 CI record. GitHub ruleset **Protect Main** is active on the default branch: pull requests, required CI checks on Python 3.10–3.13, resolved review conversations, squash-only merges, no force pushes/deletions, no bypass actors.
- **Checks:** PR #13 workflow run [45109477505](https://github.com/hapu/ai-workshop-template/actions/runs/45109477505) passed. Required checks are `checks (3.10)`, `checks (3.11)`, `checks (3.12)`, and `checks (3.13)`.
- **Provider safety:** No live inference was performed. Provider catalog remains empty; do not enable a model until account eligibility, exact quotas, region, external usage, and billing safeguards are verified.
- **Branch audit:** `feature/provider-usage-settlement` is 5 commits behind main with 0 unique commits; no branch deletion was performed.
- **Current work:** Proposal workflow now preserves optional workshop task ID and exact context-bundle SHA-256 alongside source, timestamp, and bundle digest. Private staging, record-integrity checks, stale-preview rejection, and terminal-safe diffs are implemented.
- **Next:** Design a separately approved file-application transaction and recovery semantics. No apply command exists; do not execute or apply imported content.
- **Safety:** Never request credentials in chat. Preserve fail-closed quota checks and approval-controlled Git changes.
