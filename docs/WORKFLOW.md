# Workflow

## Start
1. Inspect the repo and working tree (`git status --short --branch`, `git log --oneline -5`).
2. Read `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, and this file.
3. If the working tree is clean, update from the remote; if dirty, do not pull over uncommitted work.
4. For a new project, complete `docs/NEW_PROJECT.md` before the first task.
5. Pick one task from `TODO.md`. Use `python3 -m workshop task create` to track work when useful.

## During
1. Make one coherent change at a time, small enough to review.
2. Run `python3 -m unittest discover -s tests/unit -v` and `bash scripts/check-words.sh && bash tests/smoke.sh` after code or documentation changes.
3. Update docs when behavior, setup, or decisions change.
4. Never overwrite another device's uncommitted work. Use separate branches for simultaneous changes.
5. For browser assistants, generate a task handoff with `python3 -m workshop task handoff TASK_ID`; inspect returned changes before applying them.

## End
1. Summarize changes and exact check results.
2. Update `HANDOFF.md`, and update `DEVELOPMENT_LOG.md` for notable changes or experiments.
3. Review `git diff`; commit and push only when explicitly asked, and never force-push.
4. Require explicit approval before merging or publishing project changes.

## Roles when using several assistants
| Role | Job |
| :--- | :--- |
| Architect | Propose structure and technical decisions |
| Developer | Implement a defined task |
| Debugger | Reproduce and diagnose defects |
| Reviewer | Check changes for correctness and risk |
| Tester | Run checks and report results |
| Documenter | Update docs, decisions, and handoffs |

Always verify actual files and tests rather than trusting another assistant's summary.
