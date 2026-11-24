# TODO

Prioritized template-maintenance backlog. Keep exactly one active task under **Now**. A checked item belongs in **Completed**, not in an active queue.

## Now
- [ ] Implement stage 3 of proposal application: interactive digest-bound approval, per-file no-overwrite application, verification, journaled rollback, and explicit recovery confirmation. Keep adversarial/crash tests as a separate stage.

## Next
- [ ] Add crash-injection and adversarial race tests for every journal transition, target operation, and rollback step.
- [ ] Add manual fallback instructions for when browser/API quotas are exhausted.
- [ ] Add provider-specific quota refresh for remaining dimensions only where safe official APIs expose them.
- [ ] Verify actual OpenRouter account/project quotas, external usage, region, model eligibility, and billing safeguards before adding any enabled model policy.
- [ ] Add measured, fail-closed fallback only between independently verified free models; never substitute a paid or unknown model.
- [ ] Consider encrypted ledger export/import or a shared multi-device ledger.
- [ ] Reconcile usage from other devices and browser/API tools before enabling any adapter.

## Later
- [ ] Add opt-in project checks and isolated execution.
- [ ] Add branch preparation and approval-gated pull-request helpers.
- [ ] Add rollback/recovery procedures for approved Git operations.
- [ ] Add scheduled provider re-verification and end-to-end tests for routing, free-only enforcement, and recovery.

## Blocked / decision required
- [ ] Add a second provider only after OpenRouter account-level eligibility, quotas, external usage, and no-billing safeguards are verified.
- [ ] Decide whether cross-device quota sharing is worth its synchronization and privacy costs.

## Completed
- [x] Python 3.10+ standard-library CLI, task/checkpoint persistence, atomic writes, locking, recovery, and checksummed portable bundles.
- [x] Allowlisted bounded context, symlink containment, and resumable handoffs.
- [x] Provider-neutral contract, empty-by-default model catalog, fail-closed policy, SQLite quota ledger, and atomic reservations.
- [x] External quota snapshot reconciliation, OpenRouter key-status refresh, Groq header reconciliation, and sanitized OpenRouter rate-limit diagnostics.
- [x] OpenRouter adapter behind the shared quota gate, with exact model pinning, no retries, and no provider fallback.
- [x] Safe proposal intake: bounded versioned bundles, path/protected-file checks, expected hashes, private staging, integrity checks, stale-preview rejection, and terminal-safe read-only diffs.
- [x] Optional task ID and context-bundle SHA-256 provenance for proposals.
- [x] Approve the proposal-application safety design with POSIX, rollback, existing-parent-only, and interactive-approval decisions.
- [x] Stage 1 POSIX filesystem primitives and advisory locks; merged by PR #23.
- [x] Stage 2 canonical journal, durable private backup/prepared payloads, lock-held snapshots, and read-only recovery inventory; merged by PR #24.
- [x] Protected main branch, required Python 3.10–3.13 CI, and squash-only PR workflow.
