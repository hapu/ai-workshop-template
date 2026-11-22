# New Project Setup

Use this checklist after creating a repository from the template. Delete steps that do not apply.

## 1. Fill context
- [ ] `PROJECT_CONTEXT.md`: goal, scope, constraints, testable definition of done, current state.
- [ ] `TODO.md`: one active task under Now, then Next and Later.
- [ ] `HANDOFF.md`: date, branch, completed work, checks, repro command, next step.
- [ ] `docs/ARCHITECTURE.md`: components, data flow, dependencies, edit boundaries.

## 2. Choose the stack
- [ ] Record the stack and versions in `AGENTS.md`.
- [ ] Record important tradeoffs in `DECISIONS.md`.
- [ ] Prefer free/open-source tools that run on the target devices.
- [ ] Add dependencies only when they solve a concrete problem; pin versions when reproducibility requires it.

## 3. Verify the starter runtime
- [ ] Run `python3 -m workshop doctor`.
- [ ] Create a sample task with `python3 -m workshop task create` and generate a handoff.
- [ ] Run `python3 -m unittest discover -s tests/unit -v`.
- [ ] Run `bash scripts/check-words.sh && bash tests/smoke.sh`.

## 4. Add project commands and checks
- [ ] Add a run command and document it in `README.md`.
- [ ] Update `AGENTS.md` with host, stack, run, and test commands.
- [ ] Extend the smoke checks with project-specific validation.
- [ ] Record setup and troubleshooting instructions.

## 5. Trim the template and start
- [ ] Remove docs and sections that do not apply.
- [ ] Keep context files under their word budgets and remove placeholder text.
- [ ] Start on a feature branch; never commit directly to `main`.
- [ ] Prompt an assistant: *"Read AGENTS.md, PROJECT_CONTEXT.md, HANDOFF.md, TODO.md, and docs/WORKFLOW.md. Inspect the working tree, then work on the first actionable TODO."*
