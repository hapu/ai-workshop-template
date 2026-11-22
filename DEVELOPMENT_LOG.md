# Development Log

Newest first, with ISO dates. Archive entries older than the last ~20 once this passes 3,000 words into a separate archive file.

## 2026-11-22
- **Change:** Added bounded project-context loading with an allowlist, per-file and aggregate word limits, and symlink containment checks. Added backward-compatible task checkpoints, resume commands, and checkpoint-aware handoffs. Expanded unit tests and documentation.
- **Checks / result:** 23/23 unit tests passed locally; CLI version and doctor checks passed; word budgets, shell syntax, local Markdown links, and the staged smoke test passed. GitHub Actions run will verify supported Python versions after push.
- **Follow-up:** Add safe task bundle import/export and stronger interrupted-write recovery tests.

## 2026-11-21
- **Change:** Added a dependency-free Python task CLI, JSON-backed task store, status and note commands, Markdown handoff generation, unit tests, GitHub Actions CI, and updated architecture/roadmap documentation. Corrected the README license identifier to match the existing GPL-3.0 license.
- **Checks / result:** Nine unit tests, CLI startup/diagnostic checks, word-budget checks, shell syntax checks, and the smoke test passed in a staged repository fixture.
- **Follow-up:** Add reliable task checkpoints and context management.

## YYYY-MM-DD
- Change or experiment:
- Checks / result:
- Follow-up:
