# TODO

Template-maintenance backlog. Keep one active task under Now and make each item verifiable.

## Now
- [x] Implement the first safe browser-assistant proposal intake slice: bounded manifest, path/hash validation, private staging, and read-only diff preview. No automatic application or command execution.
- [x] Add staged-record integrity checks, stale-target detection, and terminal-control escaping to proposal previews.
- [ ] Define explicit approval-gated apply semantics; keep file application disabled until separately reviewed.

## Next
- [x] Preserve optional task ID and context-bundle SHA-256 provenance in assistant proposal bundles.
- [x] Add atomic task writes, per-task concurrent-writer protection, and interrupted-write recovery.
- [x] Add checksummed task bundle import/export with strict validation and no-overwrite imports.
- [x] Add local atomic request/token quota reservations and adapter runner.
- [x] Import external provider quota snapshots and combine them with subsequent local reservations.
- [x] Import Groq's documented RPD and combined TPM response headers; account for combined token reservations.
- [x] Add authenticated OpenRouter key-status refresh for the documented daily free-model request counter and display the `is_free_tier` account-history flag; monetary budget fields remain informational.
- [x] Add sanitized OpenRouter HTTP rate-limit classification and reset metadata; no automatic retry or fallback.
- [ ] Add complete provider-specific quota handling for remaining dimensions where safe APIs exist.
- [ ] Add optional encrypted ledger export/import or a shared ledger for multi-device usage.
- [ ] Design measured, fail-closed fallback behavior between independently verified free models.

## Later
- [ ] Verify actual OpenRouter account/project quotas, external usage, and billing safeguards before adding the first enabled model policy.
- [ ] Add Git branch preparation and approval-gated pull-request helpers.

## Blocked / needs decision
- [ ] Add a second provider only after OpenRouter account-level eligibility, quota, and no-billing safeguards are verified.
