# TODO — SAT XML Manager test

Keep one active task under **Now**. Separate confirmed evidence from assumptions.

## Now
- [ ] Identify and inspect the actual SAT XML Manager source repository/revision; establish a reproducible baseline before editing.

## Next
- [ ] Reproduce the SAT `FechaFinal` rejection and trace the exact frontend payload through Flask to sanitized SOAP serialization.
- [ ] Determine why the local endpoint maps the SAT business rejection to HTTP 502; define correct response mapping.
- [ ] Identify the exact URL, method, and initiator for the independent 404.
- [ ] Inventory tests, coverage, dependency versions, security controls, and Chromebook runtime constraints.
- [ ] Produce a prioritized gap analysis of the app and the workshop workflow based on evidence.

## Later
- [ ] Add date parsing, boundaries, ordering, and SAT serialization regression tests.
- [ ] Audit SAT authentication, request lifecycle, polling, ZIP retrieval, multi-RFC isolation, and credential lifecycle.
- [ ] Verify import/deduplication, managed RFC separation, six-sheet Excel export, and partial-payment/currency behavior.
- [ ] Review SQLite backup/restore, release packaging, resource usage, and operational recovery.

## Blocked
- [ ] Application implementation and automated tests are blocked until the actual source repository or archive is available.
- [ ] Live SAT integration tests are blocked pending a safe test strategy; never use real e.firma secrets in AI prompts or repository fixtures.

## Completed
- [x] Created isolated workshop branch `test/sat-xml-manager` from `main`.
- [x] Recorded the project handoff, reported defects, constraints, and first investigation criteria.
