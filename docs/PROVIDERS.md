# Providers

Limits, model names, pricing, terms, and eligibility change. Verify each row from an official source and update the date. Leave a cell as `unverified` until checked. Never copy a row from another project without re-checking it.

## Verification protocol
- Use the provider's official pricing, rate-limit, model, regional-availability, or terms page.
- Separate permanent free access from trials, promotional credits, and conditional grants.
- Record model identifier, input/output prices, per-request token limits, request quotas, eligible regions/account types, and expiry rules.
- Record the exact verification date, recheck/expiry date, and official HTTPS pricing and terms links.
- Record uncertainty rather than guessing. If any required field cannot be verified, do not enable the model.
- Re-verify every 90 days or before relying on a limit.
- Keep historical corrections in the verification log; do not silently overwrite a removed limit.

## Local policy catalog

`workshop/providers/policy.py` implements a fail-closed preflight. The tracked `config/provider-catalog.example.json` is intentionally empty. Copy it to the gitignored `config/provider-catalog.json` only after completing official-source verification. The gate requires:

- `enabled: true`, `access_type: free_tier`, and `verification_status: verified`
- valid `verified_at` and future `expires_at` dates
- HTTPS `source_url` and `terms_url` fields, which a maintainer must verify as official sources
- exact zero input and output price
- explicit allowed region codes and maximum input/output token limits

Unknown models, malformed policies, expired entries, non-zero prices, and requests outside the listed region or token limits are denied. The preflight is local-only and does not contact a provider. HTTPS validation is not proof that a URL is an official provider source. No provider-specific adapters or approved model entries are included in this template yet.

The current preflight does not track live account quota consumption, concurrent requests, or provider-side charges. It is not by itself sufficient to enable an API adapter. Add conservative usage reservations/accounting and configure provider-side spending limits where available before sending requests.

## Providers to evaluate

| Provider | Access type | Models / limits | Last verified | Official source |
| :--- | :--- | :--- | :--- | :--- |
| Google AI Studio / Gemini | unverified | unverified | | https://ai.google.dev/gemini-api/docs/pricing |
| Groq | unverified | unverified | | https://console.groq.com/docs/rate-limits |
| Cerebras | unverified | unverified | | https://inference-docs.cerebras.ai/ |
| Mistral | unverified | unverified | | https://docs.mistral.ai/ |
| NVIDIA NIM | unverified | unverified | | https://build.nvidia.com/ |
| Cloudflare Workers AI | unverified | unverified | | https://developers.cloudflare.com/workers-ai/ |
| Hugging Face | unverified | unverified | | https://huggingface.co/docs |
| OpenRouter | unverified | unverified | | https://openrouter.ai/collections/free-models |

## Verification log

| Date | Provider / model | What changed / official source |
| :--- | :--- | :--- |
| | | |
