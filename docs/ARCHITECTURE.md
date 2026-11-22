# Architecture

This document describes the master template's current executable slice and intended extension points.

## Overview

A dependency-free Python CLI manages local tasks, resumable checkpoints, bounded context bundles, and portable handoffs. The provider-policy layer checks whether a model can be proven zero-cost before an adapter sends a request. A minimal OpenRouter adapter is present; the approved model catalog remains empty by default.

## Current components

- `workshop/cli.py` - task, context, and provider-policy commands.
- `workshop/models.py` and `workshop/task_store.py` - task/checkpoint models and JSON persistence.
- `workshop/context_manager.py` - allowlisted context loading, symlink containment, and word budgets.
- `workshop/handoff.py` - Markdown handoffs with checkpoint state.
- `workshop/providers/base.py` - provider-neutral message, response, and adapter protocol.
- `workshop/providers/policy.py` - strict catalog parsing and fail-closed free-tier preflight, including account, organization, project, and model quota boundaries.
- `workshop/providers/reconciliation.py` - validation and normalization of dashboard/API snapshots, including saved OpenRouter and Groq evidence converters.
- `workshop/providers/usage_ledger.py` - schema-versioned SQLite snapshots plus atomic reservations mapped to independent quota boundaries; combined-token quotas count input plus output reservations.
- `workshop/providers/runner.py` - the only supported adapter invocation path; policy check and quota reservation happen before `complete`.
- `workshop/providers/openrouter.py` - standard-library OpenRouter Chat Completions adapter; no retries, streaming, model fallback, or provider fallback.
- `config/provider-catalog.example.json` - empty catalog example; no model is pre-approved.
- `.workshop/` - local task/context output; ignored by Git.

## Task persistence (v2)

Task files are written to unique same-directory temporary files, fsynced, then atomically replaced. Per-task exclusive locks serialize cross-process updates; stale locks are reclaimed only when their process is gone. Recovery deletes old orphaned temporaries and never promotes incomplete writes. Versioned JSON bundles enforce a 1 MiB import cap, schema validation, SHA-256 integrity checks (not authenticity), and no-overwrite imports.

## Provider policy

A model must be enabled, classified as `free_tier`, marked verified, within its verification dates, supported in the requested region, linked to official HTTPS pricing/terms, priced at exactly zero for input and output, and within token limits. Unknown policies are denied. The local catalog is `config/provider-catalog.json` and is gitignored. Every adapter must use the gate before making network requests; the gate itself never calls providers. The OpenRouter adapter sends the exact catalog model ID and disables provider-level fallbacks.

## Context policy

Only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md` are included. Each has an explicit word limit and the complete bundle defaults to 2,500 words. Symlinks resolving outside the project root are rejected.

## Constraints and future work

- Python 3.10+; standard library only for the current runtime.
- No paid usage without explicit user approval; uncertain pricing or eligibility must fail closed.
- Automatic authenticated quota refresh and cross-device quota synchronization are not implemented. Groq header and OpenRouter key-response converters import saved evidence only. The OpenRouter chat adapter is implemented but cannot run until a verified local model policy and fresh quota snapshots are configured.
- Keep the runtime usable on a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.


## Quota boundary model (v2)

Quotas are scoped to `account`, `organization`, `project`, or exact `model`. Account uses legacy `account_scope`; organization/project require non-secret `--quota-scope TYPE=ALIAS` and matching snapshot `scope_id`. SQLite v2 adds scope mappings, backfills v1 events/snapshots, and aggregates reservations across models for shared scopes. Missing bindings or any missing, stale, expired, or mismatched snapshot blocks requests.
