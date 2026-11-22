# Roadmap

The master template is upgraded incrementally. A checked box means the behavior exists and has been verified; planned work remains unchecked.

## Phase 1: Repository foundation
- [x] Resolve the README/license mismatch by documenting the existing GPL-3.0 license.
- [x] Add a dependency-free Python CLI entry point.
- [x] Add local JSON task storage with validation and atomic writes.
- [x] Generate portable Markdown handoffs from saved task state.
- [x] Add unit tests and run them from the smoke test.
- [x] Add continuous integration for supported Python versions.

## Phase 2: Reliable task and context management
- [x] Add resumable checkpoints to task records with backward-compatible loading.
- [x] Add task resume and checkpoint CLI commands.
- [x] Add allowlisted context loading with per-file and aggregate word limits.
- [x] Reject context symlinks that resolve outside the project root.
- [x] Include checkpoint state in generated handoffs.
- [ ] Add safe task bundle import/export.
- [ ] Add stronger interrupted-write and recovery tests.

## Phase 3: Provider adapters and routing
- [ ] Define a common provider request/response interface.
- [ ] Add provider-specific adapters behind optional dependencies.
- [ ] Implement a hard free-tier eligibility and spending gate.
- [ ] Add model routing by role, rate-limit handling, and safe fallback.
- [ ] Verify model availability and quotas from official sources; record dates.

## Phase 4: Browser assistant interoperability
- [ ] Standardize browser-ready handoff prompts and bounded context packaging.
- [ ] Import assistant responses and proposed file changes safely.
- [ ] Preserve context and provenance between API and browser sessions.
- [ ] Add manual fallback instructions when API quotas are exhausted.

## Phase 5: Controlled development automation
- [ ] Add opt-in project checks and isolated execution.
- [ ] Prepare Git branches and diffs without modifying `main`.
- [ ] Require explicit approval for commits, pushes, pull requests, and merges.
- [ ] Add rollback and recovery procedures.

## Phase 6: Monitoring and maintenance
- [ ] Add quota and usage reporting without storing API secrets.
- [ ] Add scheduled provider re-verification (default: every 90 days).
- [ ] Add end-to-end tests for routing, free-only enforcement, and recovery.
