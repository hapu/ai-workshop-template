# New Project Setup

Use this checklist after creating a repo from the template. Delete steps that do not apply.

## 1. Fill context
- [ ] `PROJECT_CONTEXT.md`: goal, scope, constraints, testable definition of done, current state.
- [ ] `TODO.md`: one active task under Now, then Next and Later.
- [ ] `HANDOFF.md`: date, branch, done, checks, repro command, next step.
- [ ] `docs/ARCHITECTURE.md`: components, data flow, dependencies, edit boundaries.

## 2. Choose the stack
- [ ] Record the stack and versions in `AGENTS.md`.
- [ ] Record important tradeoffs in `DECISIONS.md`.
- [ ] Prefer free/open-source tools that run on the target devices.
- [ ] Vendor or pin dependencies if offline use matters.

## 3. Add commands
- [ ] Add a run command and document it in `README.md`.
- [ ] Update `AGENTS.md` with host, stack, run, and test commands.
- [ ] Extend `tests/smoke.sh` with project-specific checks.
- [ ] Confirm `bash scripts/check-words.sh && bash tests/smoke.sh` passes.

## 4. Trim the template
- [ ] Delete docs and sections that do not apply.
- [ ] Keep context files under their word budgets.
- [ ] Remove placeholder text from the context files.

## 5. Start
- [ ] Prompt the assistant: *"Read AGENTS.md, PROJECT_CONTEXT.md, HANDOFF.md, TODO.md, and docs/WORKFLOW.md. Inspect the working tree, then start on the first item in TODO.md."*
- [ ] Commit the initial setup on a feature branch.
