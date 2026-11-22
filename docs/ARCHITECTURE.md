# Architecture

This document describes the master template's current executable slice and intended extension points.

## Overview

A dependency-free Python CLI manages local tasks, resumable checkpoints, bounded context bundles, and portable handoffs. A separate provider-policy layer defines the future adapter contract and checks whether a model can be proven zero-cost before any future adapter sends a request. No inference adapters or approved model catalog entries are included.

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
- `config/provider-catalog.example.json` - empty catalog example; no model is pre-approved.
- `.workshop/` - local task/context output; ignored by Git.

## Provider policy

A model must be enabled, classified as `free_tier`, marked verified, within its verification dates, supported in the requested region, linked to official HTTPS pricing/terms, priced at exactly zero for input and output, and within token limits. Unknown policies are denied. The local catalog is `config/provider-catalog.json` and is gitignored. A future adapter must use the gate before making network requests; the gate itself never calls providers.

## Context policy

Only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md` are included. Each has an explicit word limit and the complete bundle defaults to 2,500 words. Symlinks resolving outside the project root are rejected.

## Constraints and future work

- Python 3.10+; standard library only for the current runtime.
- No paid usage without explicit user approval; uncertain pricing or eligibility must fail closed.
- Live provider API adapters, automatic authenticated quota refresh, and cross-device quota synchronization are not implemented. Groq header and OpenRouter key-response converters import saved evidence only.
- Keep the runtime usable on a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.


## Quota boundary model (v2)

Each policy quota has a boundary type: `account`, `organization`, `project`, or `model`. Account quotas retain the legacy `account_scope` alias; model quotas use the exact model ID. Organization and project quotas require independent non-secret aliases supplied as repeated `--quota-scope TYPE=ALIAS` arguments. Snapshot entries for organization/project boundaries must include `scope_id`; account/model snapshots remain backward-compatible and infer their identifiers.

SQLite schema version 2 adds `usage_event_scopes` and `external_quota_snapshots.scope_id`. Existing version-1 events are backfilled into account and model boundaries, and existing snapshots receive equivalent identifiers. The migration is idempotent and preserves historical event rows. Reservations aggregate across models for account/organization/project scopes and by exact model ID for model scopes. Missing bindings or any missing, stale, expired, or mismatched snapshot blocks the entire request.
