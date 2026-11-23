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

## Browser-assistant proposal intake

Assistant-generated file changes can be imported as a bounded JSON proposal for review. Staging validates repository-relative paths, rejects traversal, symlink escapes, credential-like and protected paths, limits the bundle to 256 KiB / 32 operations / 64 KiB per file, and checks the current SHA-256 before accepting updates or deletes.

Example proposal:

```json
{
  "format": "ai-workshop-file-proposal",
  "version": 1,
  "source": "browser-assistant",
  "created_at": "2026-11-23T00:00:00Z",
  "operations": [
    {
      "op": "update",
      "path": "README.md",
      "expected_sha256": "REPLACE_WITH_CURRENT_LOWERCASE_SHA256",
      "content": "# Updated README\\n"
    },
    {
      "op": "create",
      "path": "docs/new-note.md",
      "expected_sha256": null,
      "content": "# New note\\n"
    }
  ]
}
```

Stage and inspect it:

```bash
python3 -m workshop --home .workshop proposal stage proposal.json --project .
python3 -m workshop --home .workshop proposal preview PROPOSAL_ID --project .
```

The proposal ID is printed by the stage command. Staged records are private under `.workshop/proposals/`. This version only validates, stages, and displays a read-only diff. It never applies changes, runs commands, installs dependencies, calls providers, or publishes Git changes. SHA-256 detects stale files and accidental corruption; it does not authenticate the proposal author. Review every change independently.
## Provider safety gate

The provider system includes a common adapter contract, a fail-closed quota gate, and a minimal OpenRouter Chat Completions adapter. The approved model list is empty by default. The empty example catalog intentionally denies every model until you verify its current official pricing, free-tier eligibility, account/region requirements, model token limits, and terms.

```bash
# Create a local catalog; this file is ignored by Git.
cp config/provider-catalog.example.json config/provider-catalog.json

# Inspect policies you have personally verified and added.
python3 -m workshop provider list

# Preflight a request; this checks local policy and quota but makes no reservation.
python3 -m workshop provider preflight PROVIDER MODEL \
  --input-tokens 1200 --output-tokens 400 --region MX \
  --account-scope my-provider-project

# Copy and edit the example with the latest dashboard/API usage values.
mkdir -p .workshop
cp config/provider-quota-snapshot.example.json .workshop/provider-snapshot.json
# Then import it after filling in the actual source, used/limit and reset values.
python3 -m workshop provider reconcile .workshop/provider-snapshot.json

# Inspect reconciled usage and local reservations.
python3 -m workshop provider usage PROVIDER MODEL \
  --account-scope my-provider-project

# Once a verified OpenRouter policy and fresh snapshots exist, send a gated request.
# Set OPENROUTER_API_KEY in your shell environment first.
python3 -m workshop provider chat exact/model-id:free \
  --message "Explain the current task architecture." \
  --input-tokens 1200 --max-output-tokens 400 --region MX \
  --account-scope openrouter-personal
```

The gate denies unknown, disabled, trial-only, unverified, expired, non-zero-priced, region-ineligible, or over-limit model policies. It requires current official HTTPS pricing and terms sources, per-request token limits, and quota windows. `provider preflight` is read-only and does not reserve usage. All adapters must use `execute_with_free_tier_gate` from `workshop/providers/runner.py`: it verifies the policy, atomically reserves quota in SQLite, and only then invokes the adapter.

The local quota ledger uses `.workshop/provider-usage.sqlite3`. `--account-scope` remains the legacy account alias. Policies with organization or project quotas require separate non-secret aliases using repeated `--quota-scope TYPE=ALIAS` arguments (for example, `--quota-scope organization=my-org --quota-scope project=my-project`). Use the same alias wherever requests share that provider boundary. Do not put API keys in aliases. See `docs/PROVIDERS.md` for the quota boundary v2 model. The ledger requires a fresh external snapshot for every quota window before preflight or reservation can succeed. Snapshot age limits are specified in the model policy. Reservations made after the snapshot capture are added to provider-reported usage; earlier local reservations are assumed to be included in the snapshot.

Input token counts passed to the runner must conservatively include all system messages, project context, and user messages; this package does not estimate tokens automatically. Maximum output tokens are reserved. Neuron-metered requests are rejected unless the model policy contains a Neuron quota. Reservations are not refunded after ambiguous transport failures.

The ledger counts only requests routed through this local installation and database. It does not fetch provider balances or see usage from other machines, browser assistants, or external apps. If an external snapshot is missing, stale, expired, or disagrees with the verified quota limit, requests are denied. A CLI preflight is read-only; the runner's atomic reservation is the call-time gate. Neither local control is a provider-side billing guarantee.

### Import provider usage

Generic snapshot format: copy `config/provider-quota-snapshot.example.json`, then fill in the exact provider, model, non-secret account scope, capture time, source, quota usage, verified limit, and provider reset time. Import it with `provider reconcile FILE`. The importer rejects credentials in the JSON, stale/future capture times, unknown quota windows, mismatched limits, and invalid reset times. A partial snapshot can be imported, but requests remain blocked until every quota window in the model policy has a fresh matching snapshot.

For OpenRouter, save the sanitized JSON body from `GET https://openrouter.ai/api/v1/key` and convert its daily free-model request counter with:

```bash
python3 -m workshop provider reconcile-openrouter-key /tmp/openrouter-key-status.json \
  --model "exact/model-id:free" --account-scope openrouter-personal \
  --captured-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

OpenRouter's key endpoint provides the free-model daily request count, not every per-minute/model-provider quota. Other required windows still need their own current snapshot. Do not put the API key or Authorization header in the saved response file. See `docs/PROVIDERS.md` for provider-specific limits and the snapshot format.

Groq response headers can be imported from a sanitized JSON map using `python3 -m workshop provider reconcile-groq-headers FILE --model MODEL --account-scope ORG_ALIAS --captured-at UTC_TIMESTAMP`. This imports only account-scoped requests/day and combined tokens/minute when the policy defines matching limits. The ledger counts input plus reserved output tokens for the combined token metric. It does not fetch headers itself; other documented Groq limits still require separate reconciliation. See `docs/PROVIDERS.md` for the exact format and caveats.

The OpenRouter adapter is available through `provider chat`, but no model entries are approved by default. It disables provider-level fallbacks and never retries. The provider comparison and official sources are in `docs/PROVIDERS.md`.

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
- Treat `.workshop/`, task descriptions, generated handoffs, and the local usage ledger as private project data.
- Keep `config/provider-catalog.json` local. Do not add a model until official sources support every policy field.
- No paid model use without explicit approval. `provider chat` can make a request only after the local policy gate and fresh quota snapshots approve it.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
