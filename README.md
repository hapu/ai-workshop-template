# AI Workshop Template

A provider-agnostic starter repository for AI-assisted software development from an Android phone and a low-power Chromebook. It includes a dependency-free Python CLI for task tracking, bounded context bundles, resumable handoffs, and a fail-closed provider eligibility check.

## Requirements

- Python 3.10 or newer
- Git
- Bash for repository checks
- No Python packages are required

## Quick start

Run commands from the repository root:

```bash
python3 -m workshop doctor

# Create a task and add resumable steps.
python3 -m workshop task create "Implement the first feature" \
  --description "Describe the objective and acceptance criteria."
python3 -m workshop task checkpoint add TASK_ID "Inspect existing architecture"
python3 -m workshop task checkpoint add TASK_ID "Implement and test the feature"
python3 -m workshop task resume TASK_ID

# Build a bounded project-context bundle.
python3 -m workshop context build --project . --max-words 2500 \
  --output .workshop/context-bundle.md

# Export task state for another assistant.
python3 -m workshop task handoff TASK_ID --output .workshop/task-handoff.md
```

Task data and generated context bundles are stored locally under `.workshop/` and excluded from Git. To use another task-data directory, pass `--home PATH` before the command.

## Provider safety gate

The provider system currently supplies a common adapter contract and a local preflight gate. It does not contain live provider adapters or an approved model list. The empty example catalog intentionally denies every model until you verify its current official pricing, free-tier eligibility, account/region requirements, model token limits, and terms.

```bash
# Create a local catalog; this file is ignored by Git.
cp config/provider-catalog.example.json config/provider-catalog.json

# Inspect policies you have personally verified and added.
python3 -m workshop provider list

# Preflight a request; this never makes a network call.
python3 -m workshop provider preflight PROVIDER MODEL \
  --input-tokens 1200 --output-tokens 400 --region MX
```

The gate denies unknown, disabled, trial-only, unverified, expired, non-zero-priced, region-ineligible, or over-limit model policies. It validates that source and terms links use HTTPS, but it cannot independently prove that a link is official or that a provider's live account quota remains unused. A human must verify the cited official sources, and future adapters must add usage/quota accounting and call the gate before sending a request. Do not treat a preflight as an actual inference call or a provider-side spending cap.

## Context bundles

The context builder reads only `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, `docs/ARCHITECTURE.md`, and `docs/WORKFLOW.md`. It enforces per-file word limits and a total bundle budget, ignores unrelated files (including `.env`), and rejects symlinks that escape the project root.

## Use this repository as a template

1. On GitHub, select **Use this template → Create a new repository**.
2. Follow `docs/NEW_PROJECT.md` and fill in the project context files.
3. Update `AGENTS.md` with the project's host, stack, run command, and test command.
4. Keep project-specific information in the copied repository, not in this master template.

## Validate the repository

```bash
python3 -m unittest discover -s tests/unit -v
bash scripts/check-words.sh
bash tests/smoke.sh
```

GitHub Actions runs the checks with Python 3.10–3.13.

## Security and cost controls

- Never commit API keys, tokens, passwords, private keys, or `.env` files.
- Treat `.workshop/`, task descriptions, and generated handoffs as private project data.
- Keep `config/provider-catalog.json` local. Do not add a model until official sources support every policy field.
- No paid model use without explicit approval. The CLI and policy gate make no model requests.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
