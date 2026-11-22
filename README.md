# AI Workshop Template

A provider-agnostic starter repository for AI-assisted software development from an Android phone and a low-power Chromebook. It includes reusable project instructions plus a small, dependency-free Python CLI for task tracking and assistant handoffs.

## Requirements

- Python 3.10 or newer
- Git
- Bash for the repository checks
- No Python packages are required for the starter CLI

## Quick start

Run commands from the repository root:

```bash
# Check the local environment; this does not contact an AI provider.
python3 -m workshop doctor

# Create and inspect a task.
python3 -m workshop task create "Implement the first feature" \
  --description "Describe the objective and acceptance criteria."
python3 -m workshop task list

# Use the task ID printed by the create command.
python3 -m workshop task show TASK_ID
python3 -m workshop task status TASK_ID in_progress
python3 -m workshop task note TASK_ID "Record an important finding"
python3 -m workshop task handoff TASK_ID --output HANDOFF_TASK.md
```

Task data is stored locally under `.workshop/tasks/` by default and is excluded from Git. To use another location, pass `--home PATH` before the command:

```bash
python3 -m workshop --home /path/to/workshop-data task list
```

The CLI currently manages task metadata and handoff documents. It does **not** call model APIs, automate browser assistants, execute generated code, or manage Git commits. Those capabilities are planned separately; no provider credentials are needed for this initial slice.

## Use this repository as a template

1. On GitHub, select **Use this template → Create a new repository**.
2. Follow `docs/NEW_PROJECT.md` and fill in `PROJECT_CONTEXT.md`, `TODO.md`, `HANDOFF.md`, and `docs/ARCHITECTURE.md` for the new project.
3. Update `AGENTS.md` with the project's host, stack, run command, and test command.
4. Keep project-specific information in the copied repository, not in this master template.

## First session prompt

> Read `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, and `docs/WORKFLOW.md`. Inspect the working tree and current branch, then start on the first actionable item in `TODO.md`.

## Validate the repository

```bash
bash scripts/check-words.sh
bash tests/smoke.sh
```

The smoke test also runs the Python unit tests when Python 3 is installed.

## Security and cost controls

- Never commit API keys, tokens, passwords, private keys, or `.env` files.
- Keep local task data private; handoffs may contain project paths and task descriptions.
- No paid model use without explicit approval. This CLI makes no model requests.
- Verify provider availability, limits, regions, and terms from official sources before relying on a free tier.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
