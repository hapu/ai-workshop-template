# Development Log

Newest first, with ISO dates. Archive older entries after ~20 entries or 3,000 words.

## 2026-11-22 (quota reservations)
- **Change:** Added a SQLite-backed local quota ledger with atomic multi-window reservations, account/model scopes, request/token/Neuron tracking, and a shared provider runner that reserves before adapter execution. Added usage/preflight CLI commands, conservative-token-estimate documentation, and provider free-access assessment. No live adapters or enabled models were added.
- **Checks / result:** 53 unit tests passed locally, including concurrent-reservation and fake-adapter tests that verify policy/quota denials prevent provider invocation. Python compilation, CLI/version and empty-catalog checks, word budgets, and shell syntax passed. The full smoke script passed; its Git-tracked-secret check was skipped because the local staging folder is not a Git checkout. Hosted CI for this commit remains to be checked.
- **Follow-up:** Reconcile provider dashboard usage and account-specific limits before considering the first live adapter.

## 2026-11-22
- **Change:** Added the provider-neutral adapter protocol and a local, empty-by-default model catalog. Added a fail-closed free-tier preflight for verification status/dates, official HTTPS pricing and terms, explicit region eligibility, exactly-zero input/output pricing, and token limits. Added provider list/preflight CLI commands; no live API adapters or model approvals were added.
- **Checks / result:** 35/35 unit tests passed locally. CLI, word-budget, shell syntax, and staged smoke checks passed. GitHub Actions verified supported Python versions after push.
- **Follow-up:** Verify current official provider terms and only then add the first provider/model entry and adapter. Add quota accounting before enabling live requests.

## 2026-11-22 (earlier)
- **Change:** Added bounded project-context loading with an allowlist, per-file and aggregate word limits, and symlink containment checks. Added backward-compatible task checkpoints, resume commands, and checkpoint-aware handoffs.
- **Checks / result:** 23/23 unit tests passed locally and GitHub Actions passed on Python 3.10–3.13.
- **Follow-up:** Define provider interfaces and enforce a fail-closed spending gate.

## 2026-11-21
- **Change:** Added a dependency-free Python task CLI, JSON-backed task store, status and note commands, Markdown handoff generation, unit tests, GitHub Actions CI, and corrected the README license reference to GPL-3.0.
- **Checks / result:** Nine unit tests and repository checks passed.
