# Security

## Secrets and local state
- Never commit API keys, passwords, tokens, private keys, or `.env` files.
- Keep secret files in `.gitignore`; keep only variable names in `config/examples/env.example`.
- Store keys in environment variables via a shell profile (`chmod 600`) or a password manager. Do not sync plaintext secret files through cloud storage.
- Never paste secrets into Markdown context files, task descriptions, or handoff prompts.
- `.workshop/` stores local task descriptions, notes, project paths, generated context bundles, quota snapshots, and the SQLite usage ledger. Treat it as private and keep it out of Git.
- External quota snapshot files contain account usage metadata. Never include API keys, Authorization headers, cookies, or secret fields. The importer rejects known credential field names.
- `config/provider-catalog.json` is a local policy file and is ignored by Git. The tracked example intentionally contains an empty model list.

## Browser-assistant proposals

Proposal bundles are untrusted data, never executable instructions. The importer enforces strict JSON schema and size limits, repository-relative paths, symlink containment, protected metadata/configuration and credential-path exclusions, unique targets, and expected SHA-256 preconditions for existing files. Staging writes only to private `.workshop/proposals/` storage. Version-two staged records bind the canonical repository root path, device, and inode; older records remain previewable but must be restaged before application. Preview rechecks every target and recomputes diffs from current content rather than trusting stored preview text. Optional task IDs and context-bundle SHA-256 values preserve non-secret provenance without copying context contents into the proposal.

Application is a separate POSIX-only interactive command. It requires the complete staged-record SHA-256 digest and the exact confirmation line `APPLY PROPOSAL_ID FULL_DIGEST`; non-interactive use is rejected. Before writes, it revalidates the record, repository identity, operation metadata, current target hashes and in-memory snapshots. It uses descriptor-relative no-follow traversal, private advisory locks, durable private backups and prepared files, same-directory no-overwrite installation, a per-operation journal, and automatic rollback on application failure. Interrupted transactions require a separate interactive recovery command bound to the full journal SHA-256. Recovery rolls back by default; a committed transaction can only undergo verified quarantine cleanup.

The staged-record checksum is unkeyed and can be recomputed, so it detects accidental corruption and binds the user's approval to the exact staged record but does not prove author identity. The journal checksum is likewise not a cryptographic signature; recovery confirmation binds the operator's action to the journal currently displayed. Multi-file application is recoverable but is not atomically visible as a group to external observers. Advisory locks coordinate cooperating processes only; they cannot prevent non-cooperating processes running as the same user from racing filesystem changes. No proposal content is executed, and application does not run shell commands, install dependencies, call providers, or perform Git commits/pushes. Review provenance, every diff, and the recovery inventory manually.

## Provider and spending controls
- The provider preflight denies unknown, disabled, trial-only, unverified, expired, region-ineligible, non-zero-priced, or over-limit models.
- The local quota ledger reserves requests/token units atomically before inference; all adapters must use `execute_with_free_tier_gate`, not raw provider methods.
- Use the same non-secret `account_scope` alias for every credential and local task using the same provider account. A new alias can reset local accounting, so do not create additional aliases for one account to evade a limit.
- The local ledger cannot see usage from other devices/apps. Check the actual provider dashboard before every adapter is enabled and block calls when external usage is unknown.
- Every quota window requires a fresh provider/dashboard snapshot; missing, stale, expired, or limit-mismatched snapshots block the request.
- Preflight is not a reservation and must never be treated as approval to send.
- Imported snapshots are only as complete as the captured source data. A snapshot for one limit dimension does not prove that other request/token limits are reconciled.
- A reservation is not refunded after timeouts or ambiguous failures; the provider may have received the request.
- Pricing and eligibility must be backed by current official HTTPS sources and an expiry date.
- Every provider adapter must call the gate before every request. The OpenRouter adapter sends an exact model ID, sets `provider.allow_fallbacks` to `false`, and never retries. No adapter may silently fall back to an unknown or paid model.
- The tracked model catalog stays empty. A configured OpenRouter key alone is not permission to send; policy and fresh quota snapshots must pass first.
- The local policy gate is not an account spending cap and does not guarantee provider-side availability. Configure provider-side limits when available.
- Follow provider terms and rate limits. Do not create extra accounts or keys to evade quotas.
- No paid usage without explicit approval.
