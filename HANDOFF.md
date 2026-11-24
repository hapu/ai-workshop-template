# Handoff — SAT XML Manager

- **Date:** 2026-11-23
- **Repository:** `hapu/ai-workshop-template`
- **Branch:** `test/sat-xml-manager`, created from `main`.
- **Purpose:** Use the workshop with an existing application and identify missing workflow/template capabilities.
- **Application source:** Unknown. No SAT XML Manager GitHub repository URL or source tree has been confirmed. Do not mistake this template branch for the app source.
- **Reported stack:** Flask, HTML/CSS/JavaScript, SQLite; Python 3.13.5; target Chromebook has Celeron N4500, 4 GB RAM, and about 15 GB Linux storage.
- **Reported defects:** SAT returns `CodEstatus=301` for invalid `FechaFinal`; local `POST /api/sat/requests` returns 502; separate 404 with URL/initiator unknown. No fix is verified.
- **Next:** Obtain the app repository URL or source archive. Inspect branch/status/tree/instructions/dependencies/tests. Then reproduce and diagnose FechaFinal, the 502 mapping, and the independent 404 before implementation.
- **Required sanitized evidence:** Network payload for `POST /api/sat/requests`; full 404 URL and initiator; route/function constructing the SAT request; SOAP XML with certificates, signatures, tokens, and taxpayer data removed.
- **Safety:** Never request or commit e.firma secrets. Do not add real taxpayer records to fixtures. Historical feature/version claims remain unverified.
- **Checks:** No application checks have been run because the application source is not present in this repository.

This branch is a project-specific test setup. Keep `main` unchanged and use PR review for any eventual template improvements.
