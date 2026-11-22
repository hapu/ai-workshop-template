# AI Workshop Template

A provider-agnostic starter repository for AI-assisted software development from an Android phone and a low-power Chromebook. It includes reusable project instructions plus a small, dependency-free Python CLI for task tracking, bounded context bundles, and resumable assistant handoffs.

## Requirements

- Python 3.10 or newer
- Git
- Bash for repository checks
- No Python packages are required

## Quick start

Run commands from the repository root:

```bash
# Check the local environment; this does not contact an AI provider.
python3 -m workshop doctor

# Create a task and break it into resumable steps.
python3 -m workshop task create "Implement the first feature" \
  --description "Describe the objective and acceptance criteria."
python3 -m workshop task checkpoint add TASK_ID "Inspect existing architecture"
python3 -m workshop task checkpoint add TASK_ID "Implement and test the feature"
python3 -m workshop task resume TASK_ID

# Mark a step complete using its checkpoint ID.
python3 -m workshop task checkpoint complete TASK_ID CHECKPOINT_ID

# Build a bounded context bundle from approved project files.
python3 -m workshop context build --project . --max-words 2500 \
  --output .workshop/context-bundle.md

# Export task state for another assistant.
python3 -m workshop task handoff TASK_ID --output .workshop/task-handoff.md
```

Task data and generated context bundles are stored locally under `.workshop/` by default and excluded from Git. To use another task-data directory, pass `--home PATH` before the command:

```bash
python3 -m workshop --home /path/to/workshop-data task list
```

The context builder reads only the known files `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md`. It enforces each file's word limit and a total bundle budget, ignores unrelated files (including `.env`), and rejects context-file symlinks that escape the project root.

The CLI manages local task metadata and handoff documents. It does **not** call model APIs, automate browser assistants, execute generated code, or manage Git commits. No provider credentials are needed for these features.

## Use this repository as a template

1. On GitHub, select **Use this template → Create a new repository**.
2. Follow `docs/NEW_PROJECT.md` and fill in `PROJECT_CONTEXT.md`, `TODO.md`, `HANDOFF.md`, and `docs/ARCHITECTURE.md` for the new project.
3. Update `AGENTS.md` with the project's host, stack, run command, and test command.
4. Keep project-specific information in the copied repository, not in this master template.

## Validate the repository

```bash
python3 -m unittest discover -s tests/unit -v
bash scripts/check-words.sh
bash tests/smoke.sh
```

GitHub Actions runs the same checks with Python 3.10–3.13.

## Security and cost controls

- Never commit API keys, tokens, passwords, private keys, or `.env` files.
- Treat `.workshop/`, task descriptions, and generated handoffs as private project data.
- No paid model use without explicit approval. The local CLI makes no model requests.
- Verify provider availability, limits, regions, and terms from official sources before relying on a free tier.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
