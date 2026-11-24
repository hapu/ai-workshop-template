# Architecture — SAT XML Manager

This is an initial architecture map derived from a project handoff, not source inspection. Treat every reported component as provisional until verified against the actual repository.

## Intended application shape
- **UI:** Browser frontend using HTML, CSS, and JavaScript.
- **Local service:** Python Flask application, reportedly served at `http://localhost:8765`.
- **Persistence:** SQLite.
- **Domain:** CFDI comprobantes identified by UUID, concepts, taxes, payment complements, managed RFC profiles, and discovered counterparties.
- **Import/export:** XML and ZIP ingestion; CSV, JSON, and six-sheet Excel export are reported capabilities.
- **SAT connector:** Optional e.firma authentication, mass-download request, request ID tracking, status polling, ZIP retrieval, and import.

## Expected source layout — unverified
`app.py`, `cfdi.py`, `excel_export.py`, `reconciliation.py`, `requirements.txt`, `static/app.js`, `templates/index.html`, and `tests/`. Do not create or edit these files until the actual source tree is available.

## Data invariants to verify
- UUID uniqueness and deduplication.
- Managed RFC profiles are distinct from counterparties extracted from CFDI.
- Amounts remain separated by currency unless an explicit conversion policy exists.
- Payment reconciliation accounts for partial payments and outstanding balances.
- Credentials are not persisted unexpectedly and never appear in logs.

## SAT request flow
Load credentials for an RFC → authenticate → submit a date-filtered mass-download request → receive request ID → poll status → retrieve ZIP package(s) → import and deduplicate XML.

For the reported `FechaFinal` failure, inspect the browser date value and JSON payload, Flask route, installed SAT client version, and sanitized serialized SOAP request. The possibility that a date-only string is being sent where DateTime is expected is a hypothesis, not a confirmed root cause.

## Error boundaries
- Local input validation: actionable 400 response.
- SAT business rejection: preserve SAT status/message as a structured application response; do not automatically classify every rejection as 502.
- Network timeout: safe 502/504 diagnostic.
- Unexpected internal failure: 500 with details only in local logs.
- Browser 404: diagnose independently using exact URL, method, initiator, and expected resource.

## Unknowns / source evidence required
- Actual repository URL, branch, commit, tree, and project instructions.
- Current routes, frontend payload schema, database schema, and dependency versions.
- Whether the reported features exist and are covered by tests.
- Whether 502 originates in Flask or another local layer.
- Exact cause of the 404 and FechaFinal rejection.
- Credential lifecycle, backup/restore behavior, and end-to-end SAT connector reliability.

## Target constraints
Keep the implementation suitable for a Celeron N4500 Chromebook with 4 GB RAM and roughly 15 GB Linux storage. Prefer lightweight local tools and cloud inference; do not require Docker or a local LLM.
