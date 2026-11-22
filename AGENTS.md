# AGENTS.md

Instructions for AI coding agents. Keep under 500 words.

## Environment & Commands
- **Host:** low-power Chromebook; record its OS, RAM/CPU, and available storage.
- **Stack:** Python 3.10+ standard library for the starter CLI; add dependencies only when justified.
- **Run:** `python3 -m workshop --help` or `python3 -m workshop doctor`.
- **Task state:** `python3 -m workshop task resume TASK_ID`.
- **Context:** `python3 -m workshop context build --project . --output .workshop/context.md`.
- **Provider safety:** `python3 -m workshop provider preflight PROVIDER MODEL --input-tokens N --output-tokens N --region REGION`.
- **Test:** `python3 -m unittest discover -s tests/unit -v` and `bash scripts/check-words.sh && bash tests/smoke.sh`.

## Before changing anything
1. Inspect the repo and working tree (`git status --short --branch`, `git log --oneline -5`).
2. Read `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/WORKFLOW.md`, and `WORKSHOP.md`.
3. Verify existing work; never assume a prior assistant's summary is correct.
4. Verify provider, tool, and API facts from official docs if they may have changed.
5. Explain the plan briefly before any multi-file or structural change.

## Rules
- **Branching:** Never commit directly to `main`. Use short-lived `feature/<topic>` or `fix/<topic>` branches; review diffs before merging.
- **Output discipline:** Keep terminal output small. Pipe verbose logs to `/tmp/` or tail the last 20 lines.
- **Safety:** Never delete existing work, install dependencies, use paid APIs, or expose credentials without explicit approval.
- **Provider policy:** Unknown, unverified, expired, non-zero-priced, disabled, region-ineligible, or over-limit models must be rejected. Never bypass the preflight in a provider adapter.
- **Scope:** Stay provider-agnostic. Do not invent quotas, capabilities, or compatibility claims.
- **Editing boundaries:** Do not modify generated, vendored, or test files unless the task requires it.
- **Docs:** Update docs when behavior or setup changes; do not leave stale paths or commands.
- **Template maintenance:** Keep `PROJECT_CONTEXT.md` and `HANDOFF.md` generic for template users. Record template-level decisions and changes in `DECISIONS.md` and `DEVELOPMENT_LOG.md`.

## When you finish, report
- Files changed and why.
- Checks/tests run and exact results.
- Known limitations or decisions needed.
- Branch, commit hash, and working-tree state.
- Next recommended task.

Update `HANDOFF.md` with current state, verification commands, and next step. Do not claim a commit or push unless it actually happened.
