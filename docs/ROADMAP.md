# Roadmap

The master template is upgraded incrementally. A checked box means the behavior exists and has been verified; planned work remains unchecked.

## Phase 1: Repository foundation
- [x] Add dependency-free Python CLI, task storage, handoffs, unit tests, and CI.
- [x] Resolve the README/license mismatch by documenting the existing GPL-3.0 license.

## Phase 2: Reliable task and context management
- [x] Add resumable checkpoints with backward-compatible task loading.
- [x] Add task resume and checkpoint CLI commands.
- [x] Add allowlisted context loading with per-file and aggregate word limits.
- [x] Reject context symlinks that resolve outside the project root.
- [x] Include checkpoint state in generated handoffs.
- [ ] Add safe task bundle import/export and interrupted-write recovery tests.

## Phase 3: Provider contracts and cost safety
- [x] Define a provider-neutral request/response protocol.
- [x] Add an explicit local model-policy catalog with an empty-by-default allowlist.
- [x] Implement a fail-closed preflight for free-tier, zero-price, dates, HTTPS sources, region, and token limits.
- [x] Add CLI commands to list policies, preflight quota, and show local usage without network access.
- [x] Add SQLite quota ledger with atomic concurrent reservations and account/model scopes.
- [x] Require Neuron quota definitions for nonzero Neuron-metered requests.
- [x] Add a shared provider runner that reserves usage before invoking an adapter.
- [x] Import provider/dashboard quota snapshots and require fresh data for every quota window.
- [x] Combine imported provider usage with later local reservations without double-counting.
- [x] Convert the OpenRouter key endpoint's daily free-model counter into a snapshot.
- [x] Research current provider free-tier status and document official sources.
- [ ] Add authenticated provider quota refresh for each supported quota dimension.
- [ ] Verify current provider/model terms and account-level quotas before adding approved entries.
- [ ] Add provider adapters that call the shared runner before every request.
- [ ] Reconcile usage from other devices and browser/API tools before enabling adapters.
- [ ] Add rate-limit handling and measured fallback without paid-model substitution.

## Phase 4: Browser assistant interoperability
- [ ] Import assistant responses and proposed file changes safely.
- [ ] Preserve context and provenance between API and browser sessions.
- [ ] Add manual fallback instructions when API quotas are exhausted.

## Phase 5: Controlled development automation
- [ ] Add opt-in project checks and isolated execution.
- [ ] Prepare Git branches and diffs without modifying `main`.
- [ ] Require explicit approval for commits, pushes, pull requests, and merges.
- [ ] Add rollback and recovery procedures.

## Phase 6: Monitoring and maintenance
- [x] Add local quota usage reporting without storing API secrets.
- [ ] Add quota dashboard/API refresh and cross-device reconciliation.
- [ ] Add scheduled provider re-verification.
- [ ] Add end-to-end tests for routing, free-only enforcement, and recovery.
