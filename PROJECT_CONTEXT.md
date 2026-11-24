# Project Context — SAT XML Manager

## Goal
Use SAT XML Manager as a real-world test of the AI workshop template. The app is intended to import, store, review, reconcile, and export Mexican SAT CFDI XML records, with an optional SAT mass-download connector using e.firma.

## Scope
- **In:** Existing application assessment; CFDI XML/ZIP import; SQLite persistence; RFC profiles; CSV/JSON/Excel export; payment-complement reconciliation; SAT mass-download diagnosis; regression tests; security and operational review.
- **Out for initial assessment:** Broad redesign, unrelated feature expansion, live SAT requests using real credentials, and changes to taxpayer records.

## Environment and reported stack
- Target: Lenovo IdeaPad 3 Chromebook 15IJL6, Intel Celeron N4500, 4 GB RAM, approximately 15 GB Linux storage; Android phone for review.
- Reported runtime: Python 3.13.5, x86_64 Linux.
- Reported stack: Python Flask backend, HTML/CSS/JavaScript frontend, SQLite.
- Reported local URL: `http://localhost:8765`.
- The application source repository URL and exact current source revision are **unknown**. This workshop branch is a preparation/test harness, not verified application source.

## Reported application capabilities — not yet verified
- Multiple CFDI XML files and ZIP archives; common CFDI 3.3/4.0 fields and Retenciones.
- UUID deduplication, text/type/date filters, CSV and JSON export.
- SQLite persistence and multiple managed RFC profiles.
- Excel export with six sheets: Comprobantes, Conceptos, Impuestos, Pagos, RFCs, Resumen mensual.
- Separation of managed RFC profiles from discovered counterparties.
- Payment complement reconciliation using ImpPagado and ImpSaldoInsoluto.
- Multiple e.firma credentials associated with RFCs and an SAT mass-download/ZIP retrieval workflow. Credentials were reported as in-memory only; verify.

## Current reported defects — reproduction required
1. `POST /api/sat/requests` returns HTTP 502 in the local app path.
2. SAT response: `CodEstatus=301`, message indicates an invalid `FechaFinal`.
3. A separate browser 404 is reported; its URL and initiator are unknown.
The explicit SAT rejection concerns `FechaFinal`. The source of the local 502 and the unrelated 404 are not established. A date-only `YYYY-MM-DD` value may be involved, but this remains a hypothesis until the frontend payload, Flask route, installed SAT client version, and sanitized SOAP serialization are inspected.

## Domain and security constraints
- CFDI primary identity: UUID.
- Keep amounts separated by currency; do not aggregate currencies without a defined conversion policy.
- Keep managed RFC profiles distinct from counterparties.
- Reconciliation must account for partial payments and outstanding balances.
- Never commit or transmit e.firma certificates, private keys, passwords, tokens, signatures, signed SOAP envelopes, or real taxpayer data. Use sanitized diagnostics and synthetic fixtures only unless the user explicitly approves otherwise.
- Never claim a mass download is complete before ZIP retrieval and XML import are verified.

## Definition of done for the first investigation
- Identify the real source repository, branch, commit, and actual file tree.
- Verify the current implementation and dependency versions rather than relying on historical feature claims.
- Reproduce or precisely localize the FechaFinal rejection, local 502 mapping, and separate 404.
- Produce a prioritized evidence-based gap analysis and test plan before implementation.
