# Architecture

This document describes the current executable slice and intended extension points.

## Overview

A dependency-free Python CLI manages local tasks, resumable checkpoints, bounded context bundles, and portable handoffs. Provider requests pass through a fail-closed policy gate and local quota ledger. The OpenRouter adapter exists, but the approved model catalog remains empty by default.

## Current components

- `workshop/cli.py` - task, context, and provider-policy commands.
- `workshop/models.py`, `task_store.py` - task/checkpoint models and JSON persistence.
- `workshop/context_manager.py` - allowlisted context, symlink containment, and word budgets.
- `workshop/proposals.py` - bounded proposal validation, expected-hash checks, private staging, and read-only diffs.
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

## Planned browser-assistant proposal boundary

Implemented review boundary: accept a versioned, size-bounded JSON bundle, not executable assistant output. Each proposed file operation names a repository-relative path and expected SHA-256 of the current file, or explicitly declares a new file. Reject absolute paths, traversal, symlinks, protected state, credential-like paths, unsupported operations, duplicate paths, oversized content, and stale hashes. Stage under ignored `.workshop/proposals/`, protect records with an integrity checksum, and recheck repository preconditions when rendering a read-only diff. The checksum is not an authenticity mechanism.

Imported bundles are untrusted data. Stage them only in ignored local storage, retain task/source/context provenance, and show a read-only diff. The first implementation must not execute shell commands, install dependencies, call providers, or apply files. Any future apply action must be separate and explicitly approved, with hashes rechecked immediately before writing. Commits, pushes, pull requests, and merges remain separate approval-gated actions. Checksums detect corruption; they do not authenticate the author.
