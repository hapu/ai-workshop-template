# Development Log

Newest first, with ISO dates. Archive older entries after ~20 entries or 3,000 words.

## 2026-11-23 (session-ready repository cleanup)
- **Change:** Audited main, PRs, required CI checks, branch protection, docs, and all remaining branches. Confirmed no open PRs and all four required checks pass on main. Rewrote the handoff, populated the master-template project context, reorganized TODO into one active task plus next/later/completed sections, and corrected the development history. This is documentation-only maintenance.
- **Repository state:** Main before this cleanup was `b9bcd0622948ca5b7da5e17dfeed30930d24891a`. Twenty non-main branches remain; some are behind main and others diverged because squash merges do not preserve branch commit ancestry. No branch was deleted.
- **Next:** Threat-model a separate, explicit proposal-apply transaction and recovery behavior. Keep the current importer and preview read-only.

## 2026-11-23 (handoff refresh, PR #21)
- **Change:** Updated `HANDOFF.md` and `DEVELOPMENT_LOG.md` after proposal provenance work. PR #21 merged the handoff update.
- **Verification:** GitHub Actions run [45114986537](https://github.com/hapu/ai-workshop-template/actions/runs/45114986537) passed Python 3.10–3.13.

## 2026-11-23 (proposal provenance, PR #20)
- **Change:** Added optional validated `task_id` and `context_sha256` fields to proposal bundles. Staged records preserve and display these provenance references without copying private context content. PR #19 was closed unmerged after the architecture document exceeded its word budget; PR #20 contains the corrected change.
- **Verification:** GitHub Actions run [45114855292](https://github.com/hapu/ai-workshop-template/actions/runs/45114855292) passed Python 3.10–3.13; 130 unit tests passed.

## 2026-11-23 (proposal apply safety design, PR #18)
- **Change:** Updated the roadmap and handoff to separate delivered read-only proposal review from a future approval-gated apply transaction. No apply command or file-writing behavior was added.
- **Verification:** PR #18 merged after its four required Python CI checks passed.

## 2026-11-23 (proposal review hardening, PR #17)
- **Change:** Added staged-record integrity validation, schema revalidation, current-file and create-target stale checks at preview time, bounded reads, and terminal-control escaping. Updated security and architecture documentation. PR #17 merged after the full CI matrix passed.
- **Verification:** GitHub Actions run [45114426832](https://github.com/hapu/ai-workshop-template/actions/runs/45114426832) passed Python 3.10–3.13.

## 2026-11-23 (proposal intake, PR #16)
- **Change:** Added bounded versioned JSON proposal bundles, repository-relative path and protected-path validation, expected SHA-256 preconditions, private staging under ignored `.workshop/proposals/`, and read-only diff previews. PR #15 was closed unmerged after a test assertion correction; PR #16 contains the verified implementation.
- **Verification:** PR #16 merged after its required Python CI matrix passed. No file application, command execution, provider calls, or Git publication was added.

## 2026-11-22 (proposal workflow documentation, PR #14)
- **Change:** Documented the browser-assistant proposal boundary and staged review workflow before implementation. PR #14 merged after its required CI checks passed.

## 2026-11-22 (post-PR #13 stabilization and proposal workflow design)
- **Change:** PR #13 merged after its Python 3.10–3.13 CI matrix passed. Verified the active `Protect Main` repository ruleset: default-branch targeting, pull requests, four required CI checks, conversation resolution, squash-only merges, blocked force pushes/deletions, and an empty bypass list. Audited `feature/provider-usage-settlement`: five commits behind `main`, zero unique commits; left the stale branch untouched.
- **Next milestone:** Define a browser-assistant proposal intake boundary. Imported responses and file changes must be treated as untrusted data, validated and staged, then shown as a read-only diff. No command execution or automatic file application is in scope for the first slice.
- **Verification:** PR #13 GitHub Actions run [45109477505](https://github.com/hapu/ai-workshop-template/actions/runs/45109477505) completed successfully. No provider inference or paid API usage was performed.

## 2026-11-22 (OpenRouter account tier metadata)
- **Change:** Parse and display the documented `is_free_tier` boolean from `GET /api/v1/key`. A missing value remains unknown; malformed values are rejected. Documentation clarifies that the flag means whether the user has previously paid for credits, not whether a specific model is eligible or billing safeguards are disabled. No live request or inference was made.
- **Verification:** Added tests for true, false, missing, and malformed flag values. GitHub Actions run [45087426550](https://github.com/hapu/ai-workshop-template/actions/runs/45087426550) passed on Python 3.10–3.13: 113 unit tests, word-budget checks, and repository smoke tests passed.
- **Safety:** The refresh remains one authenticated GET, no redirects/retries; no account identifiers, credentials, or model approval are added to tracked files.


## 2026-11-22 (OpenRouter rate-limit diagnostics)
- **Change:** The adapter now parses bounded HTTP error JSON and documented rate-limit headers, exposing safe status, limit-source, upstream provider code, Retry-After, and free-tier reset details. Response bodies, prompt text, and credentials remain hidden. No automatic retry, provider/model fallback, live request, or model activation was added.
- **Verification:** Added mocked tests for OpenRouter shared free-tier 429s, upstream-provider 429s, malformed headers, body sanitization, and one-call behavior. Hosted CI passed on Python 3.10–3.13; PR #11 merged.
- **Limitations:** The key-status endpoint still does not expose per-minute usage proactively; rate-limit metadata is only available after an error. No retry scheduling or cooldown persistence is implemented.

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

## 2026-11-23
- **Change:** Merged PR #14, documenting a safe browser-assistant proposal boundary. Started `feature/assistant-proposal-intake`: added a versioned bounded JSON schema, repository path and credential/protected-path checks, expected SHA-256 preconditions, private `.workshop` staging, read-only diff previews, CLI commands, and adversarial unit tests. No apply, shell execution, provider calls, or Git publication are implemented.
- **Checks / result:** Hosted CI is pending for this feature branch; do not treat tests as passed until the Python 3.10–3.13 matrix completes.
- **Follow-up:** Review CI results and code annotations; harden staged-record integrity and stale-preview detection before considering any explicit apply workflow.

## 2026-11-23 (proposal review hardening)
- **Change:** PR #16 merged the initial safe proposal intake. Added a checksum over staged review records, schema revalidation when loading staged proposals, current-file/create-state rechecks before preview, bounded reads of existing files, and escaping of terminal control characters in diffs. Stale proposals are rejected and must be staged again. No apply operation was added.
- **Checks / result:** CI for this hardening branch is pending; verify the full Python 3.10–3.13 matrix before merge.
- **Follow-up:** Decide whether a separately approved apply workflow is desirable. Do not enable automatic application or execution of proposal content.

## 2026-11-23 (proposal review hardening merged)
- **Change:** PR #17 merged after all four required Python CI jobs passed. Staged proposal records now have integrity checks; preview revalidates schema and repository preconditions, rejects stale files/create targets, bounds existing-file reads, and escapes terminal control characters. The roadmap now distinguishes delivered review safeguards from a future, separately approved apply transaction.
- **Checks / result:** PR #17 CI run [45114426832](https://github.com/hapu/ai-workshop-template/actions/runs/45114426832) passed Python 3.10–3.13.
- **Follow-up:** Design robust explicit apply and recovery semantics before any file-writing implementation. The current CLI remains read-only.

## 2026-11-23 (proposal provenance)
- **Change:** Added optional `task_id` and `context_sha256` fields to proposal bundles. Both are strictly validated, preserved in private staged records, included in the staged-record integrity checksum, revalidated at preview, and displayed with the diff. Context content is not copied into the proposal. Updated the README, security/architecture docs, roadmap, TODO, and handoff.
- **Checks / result:** Hosted CI is pending for this branch; verify the Python 3.10–3.13 matrix before merge.
- **Follow-up:** Continue keeping proposal import/preview read-only. Design any future explicit apply operation separately.

## 2026-11-23 (proposal provenance merged)
- **Change:** PR #20 merged after the Python 3.10–3.13 matrix passed. Proposal bundles now support optional validated task IDs and context-bundle SHA-256 provenance; staged records preserve and display both without copying private context contents.
- **Checks / result:** CI run [45114855292](https://github.com/hapu/ai-workshop-template/actions/runs/45114855292) passed all four Python versions; 130 unit tests passed, including proposal security/provenance cases.
- **Follow-up:** Keep import and preview read-only. Define and threat-model a separate explicit apply transaction before considering any file-writing command.
