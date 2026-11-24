# Architecture

Current executable architecture and extension points.

## Overview

A dependency-free Python CLI manages local tasks, resumable checkpoints, bounded context bundles, and portable handoffs. Provider requests pass through a fail-closed policy gate and local quota ledger. The OpenRouter adapter exists, but the approved model catalog remains empty by default.

## Current components

- `workshop/cli.py` - task, context, provider-policy, proposal staging/preview, and proposal apply/recovery commands.
- `workshop/models.py`, `task_store.py` - task/checkpoint models and JSON persistence.
- `workshop/context_manager.py` - allowlisted context, symlink containment, and word budgets.
- `workshop/proposals.py` - bounded untrusted proposal validation, repository identity binding, expected-hash checks, private staging, and read-only diffs.
- `workshop/proposal_apply/` - POSIX-only approval, descriptor-relative filesystem access, advisory locks, durable journals, private transaction preparation, no-overwrite application, rollback, recovery inventory, and interactive recovery.
- `workshop/handoff.py` - Markdown handoffs with checkpoint state.
- `workshop/providers/base.py` - provider-neutral message, response, and adapter protocol.
- `policy.py` - strict catalog parsing and fail-closed free-tier preflight.
- `reconciliation.py` - validation and normalization of provider quota snapshots.
- `usage_ledger.py` - SQLite snapshots and atomic reservations across account, organization, project, and model scopes.
- `runner.py` - supported adapter invocation path; authorizes and reserves before calling `complete`.
- `openrouter.py` - standard-library Chat Completions adapter; no retries or provider/model fallback.
- `config/provider-catalog.example.json` - empty catalog example; no model is pre-approved.
- `.workshop/` - private local state, ignored by Git.

## Task persistence

Task files use unique same-directory temporary files, fsync, and atomic replacement. Per-task locks serialize cross-process updates. Recovery removes old orphaned temporary files but never promotes incomplete writes. Versioned bundles enforce a 1 MiB cap, schema validation, SHA-256 integrity checks, and no-overwrite imports.

## Provider policy

A model must be enabled, verified, in-date, region-eligible, linked to official HTTPS pricing/terms, priced at exactly zero, and within token limits. Unknown policies are denied. The local catalog is gitignored. Every adapter must use the shared gate; OpenRouter pins the exact catalog model and disables provider fallbacks.

## Context policy

Only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md` are included. Per-file and aggregate word budgets apply; symlinks resolving outside the project root are rejected.

## Quota boundaries and constraints

Quotas may be scoped to account, organization, project, or exact model. Organization/project scopes require non-secret aliases and matching snapshot IDs. SQLite v2 migrates legacy records and aggregates reservations across shared scopes. Missing, stale, expired, or mismatched snapshots block requests. External usage from other devices or browser tools is not automatically visible.

The runtime targets Python 3.10+ and the standard library. No paid usage is allowed without explicit approval. Automatic cross-device reconciliation is not implemented. OpenRouter inference remains unavailable until a verified local policy and fresh quota snapshots exist. Keep the runtime suitable for a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.

## Browser-assistant proposal boundary

The importer accepts a versioned, size-bounded JSON bundle, not executable assistant output. Each operation names a repository-relative path and expected SHA-256 of the current file, or explicitly declares a new file. Validation rejects absolute paths, traversal, symlinks, protected state, credential-like paths, unsupported operations, duplicate paths, oversized content, and stale hashes. Staged records bind the canonical repository path/device/inode identity and carry integrity checksums. Optional task IDs and context-bundle SHA-256 values preserve provenance without copying context contents. Checksums detect accidental corruption, not author identity.

Proposal application is separate from import and preview. On POSIX, it requires the complete staged-record SHA-256 and exact interactive confirmation, revalidates repository identity and target snapshots, and uses descriptor-relative no-follow operations, private locks, durable journals/backups, and no-overwrite installation. Application failures trigger rollback; interrupted transactions are recovered through a separate interactive command bound to the journal SHA-256. Committed transactions permit cleanup only. Missing parent directories are rejected. The workflow does not execute proposal content, run shell commands, install dependencies, call providers, or perform Git writes. Multi-file application is recoverable but not globally atomic to external observers; advisory locks coordinate cooperating processes only. Commits, pushes, pull requests, and merges remain separate approval-gated actions.
