# AGENTS.md

Instructions for AI agents working on the SAT XML Manager test project.

## Project and environment
- **Purpose:** Local-first browser app for importing, storing, reviewing, reconciling, and exporting Mexican SAT CFDI XML records; optional SAT mass-download connector using e.firma.
- **Target:** Lenovo IdeaPad 3 Chromebook 15IJL6, Intel Celeron N4500, 4 GB RAM, about 15 GB Linux storage; Android phone for review and coordination.
- **Runtime reported:** Python 3.13.5; x86_64; Linux container.
- **Reported stack:** Flask, HTML/CSS/JavaScript, SQLite; local URL `http://localhost:8765`.
- **Expected entry points:** `app.py`, `cfdi.py`, `excel_export.py`, `reconciliation.py`, `static/app.js`, `templates/index.html`, `tests/`. These are hypotheses from a prior handoff; verify the actual project source before relying on them.
- **Source repository:** Not yet identified. Do not assume the application lives in this template repository or invent a remote URL.

## Before changing anything
1. Inspect branch, status, recent commits, tracked files, and project instructions.
2. Verify the application source repository and exact commit/version being tested.
3. Read `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md`.
4. Reproduce and diagnose before patching. Distinguish confirmed facts from hypotheses.
5. Explain the plan before multi-file or structural changes.

## Safety and domain rules
- Never request, commit, log, or send e.firma certificates, private keys, passwords, tokens, signed SOAP envelopes, or taxpayer data to AI services.
- Use sanitized payloads and diagnostics only. Do not put real CFDI records in fixtures without explicit approval.
- Keep managed RFC profiles distinct from counterparties discovered in invoices.
- Never sum different currencies without an explicit conversion policy.
- Preserve partial-payment and remaining-balance semantics.
- Do not claim a SAT download succeeded until ZIP retrieval and import actually complete.
- Distinguish SAT business rejections from local validation, network failures, and unexpected internal errors.
- Do not change production data or run destructive database operations without explicit approval.

## Workflow
- Use a dedicated feature/fix branch; never commit directly to `main`.
- Keep changes narrow and assign one owner per code area.
- Verify installed dependency versions and current SAT contracts before relying on API assumptions.
- Add regression tests for date validation/serialization, error mapping, import, reconciliation, and security-sensitive behavior.
- Run the project's documented checks once the actual source and commands are known. Do not invent test commands.

## Completion report
Record changed files, exact checks and results, remaining risks, branch/commit, working-tree state, and next task. Update the handoff with verified facts only.
