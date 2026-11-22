# Architecture

This document describes the master template's current executable slice and intended extension points.

## Overview

The runtime is a dependency-free Python CLI. It manages local task metadata, resumable checkpoints, bounded project context bundles, and portable Markdown handoffs. It makes no network requests.

## Current components

- `workshop/cli.py` - command-line parsing and user-facing output.
- `workshop/models.py` - task and checkpoint models, timestamps, and allowed statuses.
- `workshop/task_store.py` - validated JSON persistence with atomic file replacement.
- `workshop/context_manager.py` - allowlisted context loading, symlink containment checks, and word budgets.
- `workshop/handoff.py` - Markdown rendering with pending/completed checkpoint state.
- `.workshop/tasks/*.json` - local task state; ignored by Git.

## Data flow

Task commands -> `TaskStore` -> validated `Task` model -> JSON file. Checkpoint state is persisted in the same task record, so a resume command can reconstruct remaining work after the CLI exits. Context commands -> `ContextManager` -> allowlisted files -> size-checked `ContextBundle` -> Markdown output. Handoff commands combine task notes and checkpoints into portable Markdown.

## Context policy

Only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md` are included. Each has an explicit word limit and the complete bundle defaults to 2,500 words. Files outside the allowlist are not read. Symlinks resolving outside the project root are rejected. Generated bundles should be written under `.workshop/` because they may contain private project context.

## Planned extension points

- Provider adapters behind a common interface.
- A model router with an explicit free-tier eligibility gate.
- Browser-assistant response import.
- A sequential workflow engine with explicit approval gates.
- Usage/quota monitoring based on verified provider sources.
- Git helpers that prepare changes but require approval for commits, pushes, and merges.

These are plans, not implemented capabilities.

## Constraints

- Python 3.10+; standard library only for the current runtime.
- No paid usage without explicit user approval; uncertain pricing or eligibility must fail closed.
- Must remain usable on a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.

## Edit boundaries

- Routine: `workshop/`, `tests/`, `docs/`, and context files.
- Keep `.workshop/`, `.env*`, credentials, and private task exports out of Git.
- Preserve `LICENSE` unless a deliberate licensing decision is recorded.
