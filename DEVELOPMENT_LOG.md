# Development Log

Newest first, with ISO dates. Archive older entries after ~20 entries or 3,000 words.

## 2026-11-22 (OpenRouter key-status refresh)
- **Change:** Added an opt-in `provider refresh-openrouter-key` command. It performs one authenticated GET using `OPENROUTER_API_KEY`, rejects redirects, caps response size, sanitizes errors, and never retries. It can use a disabled local policy to import the account's daily free-model request counter before model activation. It reports API-key credit and effective-budget remainders as informational metadata only; those monetary values are not ledger-enforced. No inference request or paid usage was made during development.
- **Verification:** Added mocked tests for request method/URL/auth header, no-redirect transport, missing credentials, sanitized HTTP errors, daily counter validation, and budget parsing. GitHub Actions run [45064179638](https://github.com/hapu/ai-workshop-template/actions/runs/45064179638) passed on Python 3.10–3.13: 107 unit tests, word-budget checks, and repository smoke tests passed. A later handoff-only update is included in PR #10; its CI rerun is pending.
- **Limitations:** The endpoint does not provide per-minute free-model rate limits or upstream model/provider quotas; no model was enabled.

## 2026-11-22 (OpenRouter adapter foundation)
- **Change:** Added a standard-library OpenRouter Chat Completions adapter and `provider chat` CLI path. Requests use the exact catalog model ID, disable provider-level fallback, disable retries, avoid logging prompt/key/response bodies on errors, and are invoked only through the shared policy gate and atomic quota ledger. No model was enabled and no live request was made.
- **Verification:** Adapter tests cover request shape, exact model pinning, disabled fallbacks, response parsing, sanitized HTTP errors, no retries, and reservation-before-network behavior. **Hosted CI:** [run 45061270564](https://github.com/hapu/ai-workshop-template/actions/runs/45061270564) passed on Python 3.10–3.13. All 99 unit tests, word-budget checks, and repository smoke tests passed.
- **Follow-up:** Verify account-specific free-tier status, exact model and quota limits, region, billing safeguards, and external usage before adding an enabled local model policy.

## 2026-11-22 (Groq quota header reconciliation)
- **Change:** Added a saved-response-header converter for Groq daily request (RPD) and combined token-per-minute (TPM) counters. Added a combined tokens quota metric calculated as input plus reserved output tokens, a provider reconcile-groq-headers CLI command, documentation, and validation tests. The converter rejects credential headers, incomplete header groups, malformed resets, and limits that differ from the verified policy. It does not make a network request.
- **Checks / result:** GitHub Actions run [44988911174](https://github.com/hapu/ai-workshop-template/actions/runs/44988911174) passed unit tests, word-budget checks, and repository smoke tests on Python 3.10, 3.11, 3.12, and 3.13. No provider adapter, model approval, credential, or inference request was added.
- **Follow-up:** Reconcile any additional Groq dashboard limits and external usage before considering a live adapter; response headers do not expose every quota dimension.
## 2026-11-22 (external quota reconciliation)
- **Change:** Added a validated external quota snapshot format and CLI import, a provider/API snapshot baseline in SQLite, freshness and reset-time enforcement for every configured quota window, and local-reservation roll-forward without double-counting. Added a converter for OpenRouter's official `GET /api/v1/key` free-model daily counter. Updated provider docs and safety rules. No live provider adapter or inference request was added.
- **Checks / result:** Added tests for missing/stale/expired snapshots, limit mismatch, secret-field rejection, duplicate import, model/account scopes, roll-forward accounting, and OpenRouter daily-counter conversion. Hosted CI for this commit remains to be checked.
- **Follow-up:** Verify the actual account/project quota values and reconcile use outside this device before enabling an adapter. Add automatic provider usage refresh only where official APIs expose the required quota dimensions.

## 2026-11-22 (quota reservations)
- **Change:** Added a SQLite-backed local quota ledger with atomic multi-window reservations, account/model scopes, request/token/Neuron tracking, and a shared provider runner that reserves before adapter execution. Added usage/preflight CLI commands, conservative-token-estimate documentation, and provider free-access assessment. No live adapters or enabled models were added.
- **Checks / result:** 53 unit tests passed locally, including concurrent-reservation and fake-adapter tests that verify policy/quota denials prevent provider invocation. Python compilation, CLI/version and empty-catalog checks, word budgets, and shell syntax passed. Full smoke tests are included in CI; hosted CI for this commit remains to be checked.
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
