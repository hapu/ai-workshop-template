# AGENTS.md

Instructions for AI coding agents. Keep under 500 words.

## Environment & Commands
- **Host:** fill in: OS, RAM/CPU, storage; keep commands light.
- **Stack:** fill in: language, runtime, and pinned versions; record vendored dependencies.
- **Test / Lint:** `bash scripts/check-words.sh && bash tests/smoke.sh`
- **Run:** fill in the project start command after setup.

## Before changing anything
1. Inspect the repo and working tree (`git status --short --branch`, `git log --oneline -5`).
2. Read `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/WORKFLOW.md`, and `WORKSHOP.md`.
3. Verify existing work; never assume a prior assistant's summary is correct.
4. Verify provider, tool, and API facts from official docs if they may have changed.
5. Explain the plan briefly before any multi-file or structural change.

## Rules
- **Branching:** Never commit directly to `main`. Use `feature/<topic>` or `fix/<topic>` branches with small, atomic commits; commit or push only when explicitly asked.
- **Output discipline:** Keep terminal output small. Pipe verbose logs to `/tmp/` or tail the last 20 lines.
- **Safety:** Never delete existing work, install dependencies, use paid APIs, or expose credentials without explicit approval.
- **Scope:** Stay provider-agnostic. Do not invent quotas, capabilities, or compatibility claims.
- **Editing boundaries:** Do not modify generated, vendored, or test files unless the task requires it.
- **Docs:** Update docs when behavior or decisions change; do not leave stale paths or commands.
- **Template maintenance:** When editing this template itself, keep `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `DECISIONS.md`, and `DEVELOPMENT_LOG.md` clean for consumers. Report template changes in the commit message.

## When you finish, report
- Files changed (what and why).
- Checks/tests run and exact results.
- Known limitations, blockers, or decisions needed.
- Branch, commit hash, and working-tree state.
- Next recommended task.

Then update `HANDOFF.md` with the current state, repro command, and branch/commit state. For template maintenance, leave the placeholder handoff clean.
