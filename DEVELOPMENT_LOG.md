# Development Log

Newest first, with ISO dates. Archive older entries after ~20 entries or 3,000 words.

## 2026-11-22
- **Change:** Added the provider-neutral adapter protocol and a local, empty-by-default model catalog. Added a fail-closed free-tier preflight for verification status/dates, HTTPS source and terms links, explicit region eligibility, exactly-zero input/output pricing, and token limits. Added provider list/preflight CLI commands; no live API adapters or model approvals were added.
- **Checks / result:** 35/35 unit tests passed locally. CLI, word-budget, shell syntax, and staged smoke checks passed. GitHub Actions will verify supported Python versions after push.
- **Follow-up:** Verify current official provider terms and only then add the first provider/model entry and adapter. Add quota accounting before enabling live requests.

## 2026-11-22 (earlier)
- **Change:** Added bounded project-context loading with an allowlist, per-file and aggregate word limits, and symlink containment checks. Added backward-compatible task checkpoints, resume commands, and checkpoint-aware handoffs.
- **Checks / result:** 23/23 unit tests passed locally and GitHub Actions passed on Python 3.10–3.13.
- **Follow-up:** Define provider interfaces and enforce a fail-closed spending gate.

## 2026-11-21
- **Change:** Added a dependency-free Python task CLI, JSON-backed task store, status and note commands, Markdown handoff generation, unit tests, GitHub Actions CI, and corrected the README license reference to GPL-3.0.
- **Checks / result:** Nine unit tests and repository checks passed.
