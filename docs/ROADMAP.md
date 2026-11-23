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
- [x] Add unique atomic task writes and per-task writer locking.
- [x] Add abandoned temporary-file recovery and crash-safety tests.
- [x] Add versioned, checksummed task bundle import/export with no-overwrite imports.

## Phase 3: Provider contracts and cost safety
- [x] Define a provider-neutral request/response protocol.
- [x] Add an explicit local model-policy catalog with an empty-by-default allowlist.
- [x] Implement a fail-closed preflight for free-tier, zero-price, dates, HTTPS sources, region, and token limits.
- [x] Add CLI commands to list policies, preflight quota, and show local usage without network access.
- [x] Add SQLite quota ledger with atomic concurrent reservations across account, organization, project, and model boundaries.
- [x] Migrate legacy quota snapshots and reservations to the independently scoped SQLite schema.
- [x] Require Neuron quota definitions for nonzero Neuron-metered requests.
- [x] Add a shared provider runner that reserves usage before invoking an adapter.
- [x] Import provider/dashboard quota snapshots and require fresh data for every quota window.
- [x] Combine imported provider usage with later local reservations without double-counting.
- [x] Convert the OpenRouter key endpoint's daily free-model counter into a snapshot.
- [x] Research current provider free-tier status and document official sources.
- [x] Add authenticated OpenRouter key-status refresh for the documented daily free-model request counter and `is_free_tier` account-history flag.
- [ ] Add authenticated refresh for other provider-specific quota dimensions where official APIs expose them.
- [ ] Verify current provider/model terms and account-level quotas before adding approved entries.
- [x] Add a minimal OpenRouter Chat Completions adapter that uses the shared runner.
- [ ] Reconcile usage from other devices and browser/API tools before enabling adapters.
- [x] Surface sanitized OpenRouter limit-source, reset, and retry-after diagnostics without automatic retries.
- [ ] Add provider-specific quota coverage and measured fail-closed fallback without paid-model substitution.

## Phase 4: Browser assistant interoperability
- [x] Define a versioned, size-bounded JSON proposal bundle for create/update/delete file operations.
- [x] Validate repository-relative paths, operation types, expected file hashes, and protected/credential-like paths before staging.
- [x] Store proposals privately under ignored `.workshop/proposals/` state with source, timestamp, and bundle-hash provenance.
- [x] Generate read-only diffs, checksum staged records, escape terminal control characters, and reject stale/conflicting previews.
- [x] Keep command execution and file application out of import/preview; no proposal content is executed or automatically applied.
- [ ] Review and approve the finalized [proposal-application safety design](PROPOSAL_APPLICATION_DESIGN.md) before implementation.
- [x] Preserve optional workshop task ID and exact context-bundle SHA-256 in proposal metadata without copying context contents.
- [ ] Add manual fallback instructions when API quotas are exhausted.

## Proposal apply safety gate (not implemented)

The proposed design is documented in [docs/PROPOSAL_APPLICATION_DESIGN.md](PROPOSAL_APPLICATION_DESIGN.md). Selected decisions: POSIX-first with fail-closed capability checks; rollback as the default interrupted-transaction recovery; existing parent directories only; and interactive confirmation bound to the full staged-record SHA-256 digest.

A future apply operation must remain a separate local CLI action, never part of import or preview. It must revalidate the staged-record checksum, repository identity, every path, and every expected file hash immediately before writes; reject symlinks and protected paths again; use descriptor-relative filesystem operations and advisory locks; and maintain a durable journal and backups for recoverable multi-file behavior. Git commits, pushes, PRs, and merges remain separate approvals. No apply or recovery command exists today.

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
