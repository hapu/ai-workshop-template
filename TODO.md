# TODO

Template-maintenance backlog. Keep one active task under Now and make each item verifiable.

## Now
- [ ] Verify actual OpenRouter account/project quotas, external usage, and billing safeguards before adding the first enabled model policy.

## Next
- [x] Add atomic task writes, per-task concurrent-writer protection, and interrupted-write recovery.
- [x] Add checksummed task bundle import/export with strict validation and no-overwrite imports.
- [x] Add local atomic request/token quota reservations and adapter runner.
- [x] Import external provider quota snapshots and combine them with subsequent local reservations.
- [x] Import Groq's documented RPD and combined TPM response headers; account for combined token reservations.
- [x] Add authenticated OpenRouter key-status refresh for the documented daily free-model request counter; monetary budget fields remain informational.
- [x] Add sanitized OpenRouter HTTP rate-limit classification and reset metadata; no automatic retry or fallback.
- [ ] Add complete provider-specific quota handling for remaining dimensions where safe APIs exist.
- [ ] Add optional encrypted ledger export/import or a shared ledger for multi-device usage.
- [ ] Design measured, fail-closed fallback behavior between independently verified free models.

## Later
- [ ] Implement browser-assistant response import and proposed-change review.
- [ ] Add Git branch preparation and approval-gated pull-request helpers.

## Blocked / needs decision
- [ ] Add a second provider only after OpenRouter account-level eligibility, quota, and no-billing safeguards are verified.
