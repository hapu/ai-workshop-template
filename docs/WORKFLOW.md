# Workflow

## Start or resume
1. Inspect the repo and working tree (`git status --short --branch`, `git log --oneline -5`).
2. Read `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, and this file.
3. If the working tree is clean, update from the remote; if dirty, do not pull over uncommitted work.
4. For a new project, complete `docs/NEW_PROJECT.md` before the first task.
5. Resume an existing task with `python3 -m workshop task resume TASK_ID`, or create one with `python3 -m workshop task create`.
6. Build a bounded context bundle with `python3 -m workshop context build --project . --output .workshop/context.md`.

## During
1. Add discrete steps with `python3 -m workshop task checkpoint add TASK_ID "Step title"`.
2. Complete steps with `python3 -m workshop task checkpoint complete TASK_ID CHECKPOINT_ID`; add findings with `python3 -m workshop task note`.
3. Make one coherent change at a time, small enough to review.
4. Before any inference adapter sends a request, verify the exact model and account policy, then invoke the adapter through `execute_with_free_tier_gate`. Never call a raw adapter directly.
5. The CLI preflight is read-only and does not reserve usage. The runner performs the local atomic reservation immediately before network I/O.
6. Use one non-secret `account_scope` for all credentials that share the same provider account/quota. The local ledger cannot see usage from other devices, browser assistants, or provider dashboards; reconcile those sources before enabling live adapters.
7. Reservations are not refunded after timeouts or ambiguous transport failures. Treat the provider as having possibly received the request.
8. Do not infer a free tier from a model name or provider reputation. Add catalog entries only after verifying official pricing, terms, model limits, account eligibility, and region.
9. Do not enable live adapters until account-specific remaining quotas are known and provider-side spending safeguards are configured where available.
10. Run `python3 -m unittest discover -s tests/unit -v` and `bash scripts/check-words.sh && bash tests/smoke.sh` after code or documentation changes.
11. Update docs when behavior, setup, or decisions change.
12. Never overwrite another device's uncommitted work. Use separate branches for simultaneous changes.

## End
1. Export a handoff with `python3 -m workshop task handoff TASK_ID --output .workshop/handoff.md`.
2. Summarize changes and exact check results.
3. Update `HANDOFF.md` and `DEVELOPMENT_LOG.md` for notable changes or experiments.
4. Review `git diff`; commit and push only when explicitly asked, and never force-push.
5. Require explicit approval before merging or publishing project changes.

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
