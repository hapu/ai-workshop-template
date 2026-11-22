# Security

## Secrets and local state
- Never commit API keys, passwords, tokens, private keys, or `.env` files.
- Keep secret files in `.gitignore`; keep only variable names in `config/examples/env.example`.
- Store keys in environment variables via a shell profile (`chmod 600`) or a password manager. Do not sync plaintext secret files through cloud storage.
- Never paste secrets into Markdown context files, task descriptions, or handoff prompts.
- `.workshop/` stores local task descriptions, notes, project paths, and generated context bundles. Treat it as private and keep it out of Git.
- `config/provider-catalog.json` is a local policy file and is ignored by Git. The tracked example intentionally contains an empty model list.

## Provider and spending controls
- The provider preflight denies unknown, disabled, trial-only, unverified, expired, region-ineligible, non-zero-priced, or over-limit models.
- HTTPS source validation does not establish source authenticity; a maintainer must verify every linked source and the policy contents.
- The current gate does not account for remaining free quotas, concurrent usage, or provider-side spending. It must not be treated as a complete no-charge guarantee.
- Before any adapter is enabled, add conservative usage reservations/accounting, enforce the gate before each call, and configure provider-side billing/spending restrictions.
- No adapter may silently fall back to an unknown or paid model.
- Follow provider terms and rate limits. Do not create extra accounts or keys to evade quotas.
- No paid usage without explicit approval.
