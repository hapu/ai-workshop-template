# TODO

Template-maintenance backlog. Keep one active task under Now and make each item verifiable.

## Now
- [ ] Verify the user's actual provider project/account quotas and reconcile usage outside this local ledger before enabling the first adapter.

## Next
- [ ] Add safe task bundle import/export and interrupted-write recovery tests.
- [x] Add local atomic request/token quota reservations and adapter runner.
- [x] Import external provider quota snapshots and combine them with subsequent local reservations.
- [ ] Add authenticated provider quota refresh and rate-limit handling where safe APIs exist.
- [ ] Add optional encrypted ledger export/import or a shared ledger for multi-device usage.
- [ ] Design measured, fail-closed fallback behavior between independently verified free models.

## Later
- [ ] Implement browser-assistant response import and proposed-change review.
- [ ] Add Git branch preparation and approval-gated pull-request helpers.

## Blocked / needs decision
- [ ] Provider integration order: choose based on current official free-tier eligibility, limits, region, and reliability.
