# AI Workshop Template

A starter repo for building software with AI assistants from a phone and a low-power Chromebook. Read `WORKSHOP.md` for the full spec.

## Use it
1. On GitHub, click **Use this template → Create a new repository**.
2. Follow `docs/NEW_PROJECT.md`: fill `PROJECT_CONTEXT.md`, `TODO.md`, `HANDOFF.md`, and `docs/ARCHITECTURE.md`.
3. Update `AGENTS.md` with the host, stack, run command, and test command.
4. Delete docs you do not need.

## First session prompt
*"Read AGENTS.md, PROJECT_CONTEXT.md, HANDOFF.md, TODO.md, and docs/WORKFLOW.md. Inspect the working tree, then start on the first item in TODO.md."*

## Check
```bash
bash scripts/check-words.sh
bash tests/smoke.sh
```

## Edit boundaries
- Edit source, docs, and context files for the task.
- Do not edit vendored or generated files unless the task requires it.
- Add project checks to `tests/smoke.sh` as the stack appears.

## Keys
Copy names from `config/examples/env.example` into your shell profile. Never commit real keys.

## License
Apache-2.0. Replace `LICENSE` if your project needs a different license.
