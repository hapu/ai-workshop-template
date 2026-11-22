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
- `workshop/providers/policy.py` - strict catalog parsing and fail-closed free-tier preflight.
- `config/provider-catalog.example.json` - empty catalog example; no model is pre-approved.
- `.workshop/` - local task/context output; ignored by Git.

## Provider policy

A model must be enabled, classified as `free_tier`, marked verified, within its verification dates, supported in the requested region, linked to HTTPS pricing/terms sources, priced at exactly zero for input and output, and within token limits. The HTTPS check does not establish that a source is official; a human must verify and maintain that evidence. Unknown policies are denied. The local catalog is `config/provider-catalog.json` and is gitignored. A future adapter must use the gate before making network requests; the gate itself never calls providers.

The current policy does not track provider-side quota consumption, concurrent reservations, or unexpected charges. Do not enable live adapters until usage accounting and provider-side spend safeguards are implemented and verified.

## Context policy

Only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md` are included. Each has an explicit word limit and the complete bundle defaults to 2,500 words. Symlinks resolving outside the project root are rejected.

## Constraints and future work

- Python 3.10+; standard library only for the current runtime.
- No paid usage without explicit user approval; uncertain pricing or eligibility must fail closed.
- Provider-specific adapters and quota tracking are not implemented yet.
- Keep the runtime usable on a low-memory Chromebook; avoid Docker, local LLMs, and heavy databases.
