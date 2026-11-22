# Security

## Secrets and local task data
- Never commit API keys, passwords, tokens, private keys, or `.env` files.
- Keep secret files in `.gitignore`; keep only variable names in `config/examples/env.example`.
- Store keys in environment variables via a shell profile (`chmod 600`) or a password manager. Do not sync plaintext secret files through cloud storage.
- Never paste secrets into Markdown context files, task descriptions, or handoff prompts.
- `.workshop/` stores local task descriptions, notes, and project paths. Treat it as private and keep it out of Git.
- Run `bash tests/smoke.sh` before committing; it checks tracked `.env` files and the local test suite.

## Device access
- Use a separate SSH key or GitHub fine-grained token for the Chromebook and phone so each can be revoked alone.
- Scope tokens to only the repositories and permissions required.

## Gateways and model APIs
- Require authentication on any LiteLLM or similar gateway; never expose an unauthenticated gateway publicly.
- A future provider adapter must enforce spending and free-tier eligibility before sending a request. Unknown pricing or eligibility must fail closed.
- Follow provider terms and rate limits. Do not create extra accounts or keys to evade quotas.
- No paid usage without explicit approval.
