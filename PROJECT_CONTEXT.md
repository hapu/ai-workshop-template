# Project Context

Keep under 800 words. This file describes the master template, not a project created from it.

## Goal
Provide a lightweight, provider-agnostic workshop for building software with AI assistants from an Android phone and a low-power Chromebook. Keep project state, context, decisions, and reviewable changes in Git while preserving human control over spending and file changes.

## Scope
- **In:** Dependency-free Python task/checkpoint CLI; bounded context and handoffs; provider-neutral adapters; fail-closed free-tier policy and quota accounting; safe import and read-only review of browser-assistant file proposals; documented PR workflow.
- **Out:** Enabled inference models by default, paid API usage without explicit approval, automatic proposal application, shell execution from assistant output, automatic provider/model fallback, heavy local model runtimes, and unattended Git publication.

## Constraints
- **Devices:** Android phone and Chromebook with Intel Celeron N4500, 4 GB RAM, and approximately 15 GB Linux storage.
- **Budget:** Free tiers only unless explicitly approved. Public claims of free access are not enough to enable a model.
- **Stack / versions:** Python 3.10+ standard library; Bash for repository checks; GitHub Actions on Python 3.10–3.13.
- **Licensing:** GPL-3.0.
- **Other:** Keep the runtime light. Treat `.workshop/` as private and untracked. Never store credentials in the repository. Use feature branches and pull requests; never push directly to protected `main`.

## Definition of done
- **Testable outcome:** Unit tests, repository smoke tests, and documentation word budgets pass.
- **User-visible behavior:** Task/context workflows are resumable; provider usage fails closed unless policy and fresh quota evidence pass; imported proposals produce only a safe, read-only preview.
- **Checks that must pass:** `python3 -m unittest discover -s tests/unit -v`; `bash scripts/check-words.sh`; `bash tests/smoke.sh`; CI on Python 3.10, 3.11, 3.12, and 3.13.

## Current state
- **What exists:** Task/checkpoint persistence, portable bundles, context builder, handoffs, provider policy and quota ledger, external quota reconciliation, OpenRouter adapter and diagnostics, and safe browser-assistant proposal intake/review with task/context provenance.
- **What runs:** The local CLI and test suite. Provider adapters are gated; the tracked provider catalog is empty.
- **What is missing:** Verified account-specific quota and billing evidence before enabling inference; multi-device quota reconciliation; a reviewed and explicitly approved proposal-apply design; manual fallback guidance for exhausted API quotas.
