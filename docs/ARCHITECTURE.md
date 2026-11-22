# Architecture

This document describes the master template's current executable slice and the intended extension points. Update it when the implementation changes.

## Overview

The first runtime feature is a local Python CLI. It manages task metadata and creates portable Markdown handoffs. It uses only the Python standard library and makes no network requests.

## Current components

- `workshop/cli.py` - command-line parsing and user-facing output.
- `workshop/models.py` - task model, timestamps, and allowed statuses.
- `workshop/task_store.py` - JSON persistence with atomic file replacement and task-ID validation.
- `workshop/handoff.py` - Markdown handoff rendering for browser or API assistants.
- `.workshop/tasks/*.json` - local task state; ignored by Git.

## Data flow

CLI command -> `TaskStore` -> validated `Task` model -> JSON file. Handoff commands load a task and render Markdown to stdout or a user-selected output file. Task files remain local unless the user explicitly copies or exports them.

## Planned extension points

- Provider adapters behind a common interface.
- A model router with an explicit free-tier eligibility gate.
- Browser-assistant prompt export and response import.
- A sequential workflow engine with explicit approval gates.
- Usage/quota monitoring based on verified provider sources.
- Git helpers that prepare changes but require approval for commits, pushes, and merges.

These are plans, not implemented capabilities. Do not write documentation or prompts that imply they already work.

## Constraints

- Python 3.10+; standard library for the initial runtime.
- Cloud inference only when a future provider adapter is explicitly configured.
- No paid usage without explicit user approval; uncertain pricing or eligibility must fail closed.
- Must remain usable on a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.

## Edit boundaries

- Routine: `workshop/`, `tests/`, `docs/`, and the context files.
- Keep `.workshop/`, `.env*`, credentials, and private task exports out of Git.
- Preserve `LICENSE` unless a deliberate licensing decision is recorded.
