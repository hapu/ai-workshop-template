# Project Context

Keep under 800 words. This file describes the master template, not a project created from it.

## Goal
Provide a lightweight, provider-agnostic workshop for building software with AI assistants from an Android phone and a low-power Chromebook. Keep project state, context, decisions, and reviewable changes in Git while preserving human control over spending, file application, and publication.

## Scope
- **In:** Dependency-free Python task/checkpoint CLI; bounded context and handoffs; provider-neutral adapters; fail-closed free-tier policy and quota accounting; safe browser-assistant proposal intake, preview, interactive POSIX application, rollback, and recovery; documented PR workflow.
- **Out:** Enabled inference models by default, paid API usage without explicit approval, unattended/non-interactive proposal application, shell execution from assistant output, automatic provider/model fallback, heavy local model runtimes, and unattended Git publication.

## Constraints
- **Devices:** Android phone and Chromebook with Intel Celeron N4500, 4 GB RAM, and approximately 15 GB Linux storage.
- **Budget:** Free tiers only unless explicitly approved. Public claims of free access are not enough to enable a model.
- **Stack / versions:** Python 3.10+ standard library; Bash for repository checks; GitHub Actions on Python 3.10–3.13.
- **Licensing:** GPL-3.0.
- **Other:** Keep the runtime light. Treat `.workshop/` as private and untracked. Never store credentials in the repository. Use feature branches and pull requests; never push directly to protected `main`.

## Definition of done
- **Testable outcome:** Unit tests, repository smoke tests, and documentation word budgets pass.
- **User-visible behavior:** Task/context workflows are resumable; provider usage fails closed unless policy and fresh quota evidence pass; proposal changes are staged and reviewed, then applied only through full-digest interactive approval with recoverable rollback.
- **Checks that must pass:** `python3 -m unittest discover -s tests/unit -v`; `bash scripts/check-words.sh`; `bash tests/smoke.sh`; CI on Python 3.10, 3.11, 3.12, and 3.13.

## Current state
- **What exists:** Task/checkpoint persistence, portable bundles, context builder, handoffs, provider policy and quota ledger, external quota reconciliation, OpenRouter adapter and diagnostics, and browser-assistant proposal staging/preview/apply/recovery.
- **Proposal safety:** POSIX-only; interactive approval bound to the complete staged-record SHA-256; existing parent directories only; private durable journals/backups; rollback for interrupted transactions; separate journal-digest-bound recovery. Multi-file operations are recoverable but not globally atomic to external observers.
- **What runs:** The local CLI and test suite. Provider adapters are gated; the tracked provider catalog is empty.
- **What remains:** Validate the end-to-end workflow on a real pilot project; verify account-specific quota and billing evidence before enabling inference; improve cross-device usage reconciliation and manual quota-exhaustion guidance.
