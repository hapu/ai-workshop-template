# Architecture

Current executable architecture and extension points.

## Overview

A dependency-free Python CLI manages local tasks, resumable checkpoints, bounded context, handoffs, provider policy, quota accounting, and browser-assistant proposals. Provider requests pass through a fail-closed policy gate and local quota ledger. OpenRouter is the first adapter; the approved model catalog remains empty by default.

## Current components

- `workshop/cli.py` - task, context, provider, proposal staging/preview, apply, and recovery commands.
- `models.py`, `task_store.py` - task/checkpoint models and JSON persistence.
- `context_manager.py`, `handoff.py` - allowlisted context bundles and resumable assistant handoffs.
- `proposals.py` - bounded untrusted bundle validation, repository identity binding, private staging, and read-only diffs.
- `proposal_apply/` - POSIX filesystem primitives, approval, advisory locks, journals, backups, no-overwrite application, rollback, and recovery.
- `providers/base.py`, `policy.py` - provider-neutral contracts and fail-closed model eligibility.
- `reconciliation.py`, `usage_ledger.py` - external quota snapshots and atomic SQLite reservations.
- `runner.py` - shared gate and reservation before adapter execution.
- `openrouter.py` - exact model pinning, no retries, and no provider fallback.
- `config/provider-catalog.example.json` - empty catalog example; no model is pre-approved.
- `.workshop/` - private local state, ignored by Git.

## Task and context persistence

Task files use unique same-directory temporary files, fsync, and atomic replacement. Per-task locks serialize cross-process updates. Recovery removes old orphaned temporary files but never promotes incomplete writes. Versioned task bundles enforce size limits, schema validation, SHA-256 integrity, and no-overwrite imports.

Context includes only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md`. Per-file and aggregate word budgets apply; symlinks resolving outside the project root are rejected.

## Provider policy and quota boundaries

A model must be enabled, verified, in-date, region-eligible, linked to official HTTPS pricing/terms, priced at exactly zero, and within token limits. Unknown policies are denied. Every adapter must use the shared gate. Quotas may be scoped to account, organization, project, or exact model; missing, stale, expired, or mismatched snapshots block requests. SQLite combines imported usage with later local reservations. Usage from other devices and browser tools is not automatically visible.

## Browser-assistant proposal workflow

Proposal bundles are untrusted data, never executable instructions. Validation rejects unsafe paths, symlinks, protected/credential-like paths, duplicate targets, oversized content, and stale hashes. Staged records bind repository path/device/inode identity and preserve optional task/context provenance without copying context contents.

Application is separate from import and preview. On POSIX it requires the complete staged-record SHA-256 and exact interactive confirmation. It revalidates target snapshots and uses descriptor-relative no-follow operations, private locks, durable journals/backups, and no-overwrite installation. Application failures trigger rollback; interrupted transactions require separate interactive recovery bound to the journal digest. Committed transactions permit cleanup only. Missing parent directories are rejected.

Multi-file application is recoverable, not globally atomic to external observers. Advisory locks coordinate cooperating processes only. Proposal content is never executed; apply/recovery do not run shell commands, install dependencies, call providers, or perform Git writes. Commits, pushes, pull requests, and merges remain separately approved.

## Runtime constraints

Target Python 3.10+ and the standard library. Keep the runtime suitable for a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases. No paid usage without explicit approval.