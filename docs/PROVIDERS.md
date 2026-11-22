# Providers

Limits, model names, pricing, terms, and eligibility change. Verify each row from official sources and update the date. Leave a cell as `unverified` until checked. Never copy a row from another project without re-checking it.

## Verification protocol

- Use the provider's official pricing, rate-limit, model, regional-availability, or terms page.
- Separate permanent free access from trials, promotional credits, and conditional grants.
- Record exact model ID, input/output prices, per-request token limits, request/token quotas, eligible regions and account types, expiry rules, and data-use terms.
- Record the exact verification date, recheck/expiry date, and official HTTPS pricing and terms links.
- Record uncertainty rather than guessing. If any required field cannot be verified, do not enable the model.
- Re-verify every 90 days or before relying on a limit.
- Keep historical corrections in the verification log; do not silently overwrite a removed limit.

## Current provider assessment

Initial research checked official provider documentation on **2026-11-21**. This is a research snapshot, not an account-level approval. No provider is enabled in the local model catalog.

| Provider | Current free-access finding | Implication for this workshop | Status |
| :--- | :--- | :--- | :--- |
| OpenRouter | The free-model collection lists model variants with $0 prompt/completion pricing. Free-model rate limits depend on the account's purchased-credit tier; the official key endpoint exposes `free_model_daily_requests` (used/limit/remaining), while the per-minute free-model limit is not returned by that endpoint. OpenRouter's documentation also notes model-specific provider capacity and global rate enforcement. | Strong first adapter candidate if an exact `:free` model ID is pinned, all paid fallback and paid variants are disabled, current account limits are obtained from the official key endpoint, and account/project usage is reconciled. Never buy credits to increase a quota; credit purchases violate the zero-spend requirement. | Candidate; account limits not verified |
| Google AI Studio / Gemini API | Selected models have free input and output token prices. Mexico is listed as a supported region. Rate limits are per project, vary by model and project tier, and must be checked in the user's AI Studio rate-limit dashboard. Daily request quotas reset at midnight Pacific time. Free-tier content may be used to improve Google's products. Some tools/grounding features have separate charges or restrictions. | Strong candidate once the user verifies the exact model and project quotas, confirms the project remains on the Free tier without billing enabled, accepts the free-tier data-use terms, and disables paid tools/grounding. Do not hard-code a generic Gemini quota from another account. | Candidate; account limits not verified |
| Groq | Limits are measured in RPM, RPD, TPM, TPD, and sometimes separate input/output token dimensions. Exact limits are organization-specific and shown in the account's Limits page. | Do not assume public example limits equal this account's Free Plan limits. Add only after the user's organization dashboard and eligibility are verified. | Unverified |
| Cloudflare Workers AI | Workers Free includes 10,000 Neurons/day; limits reset at 00:00 UTC and excess operations fail on Workers Free. Workers Paid bills usage above the allocation at $0.011 per 1,000 Neurons. Some models require paid billing or prepaid AI Gateway credits. | Potential free-allocation option only after confirming the account is on Workers Free and selecting a model that does not require paid billing. The current model policy requires exactly $0/token input and output, so it cannot yet express a metered model drawing from a free Neuron allowance; add a separate allocation policy before considering an adapter. | Not supported by current policy schema |
| Hugging Face Inference Providers | Current documentation states Free users receive no included monthly Inference Provider credits; Free users must purchase credits or upgrade to PRO. | Not eligible for the strict free-only API list. Do not confuse older documentation or historical credits with current Free access. | Not eligible under current free-only rule |
| Mistral API | Mistral Free mode includes usage for Vibe and Studio but does not include API access. Creating API keys and using the API require billing activation and pay-as-you-go. | Not eligible for a no-billing API integration. | Not eligible under current free-only rule |
| Cerebras | Developer access includes a one-time $5 promotional credit after adding a valid payment method. It expires 30 days after activation; access pauses after expiration/exhaustion unless PayGo credits are purchased. It is not an ongoing free tier. | Exclude from strict zero-budget routing. A temporary promotional balance is not a permanent free quota. | Trial/promo only; excluded |
| NVIDIA NIM | The NVIDIA Developer Program describes free hosted NIM API endpoints for prototyping, research, development, and testing. Production use requires an NVIDIA AI Enterprise license. Public documentation reviewed here did not establish dependable per-model request/token quotas or account/region availability. | Possible evaluation candidate, but don't enable until model-specific quotas, endpoint terms, region eligibility, and intended-use restrictions are verified. Do not assume free prototype access permits production workloads. | Candidate; capacity and exact terms unverified |

### Official sources checked

- OpenRouter free models and rate-limit documentation: <https://openrouter.ai/collections/free-models> and <https://openrouter.ai/docs/api_reference/limits> (the `GET /api/v1/key` endpoint reports current free-model daily requests used/limit/remaining)
- Gemini pricing, rate limits, and supported regions: <https://ai.google.dev/gemini-api/docs/pricing>, <https://ai.google.dev/gemini-api/docs/rate-limits>, and <https://ai.google.dev/gemini-api/docs/available-regions>
- Groq rate limits: <https://console.groq.com/docs/rate-limits>
- Cloudflare Workers AI pricing: <https://developers.cloudflare.com/workers-ai/platform/pricing/>
- Hugging Face Inference Providers pricing: <https://huggingface.co/docs/inference-providers/main/pricing>
- Mistral usage and limits: <https://docs.mistral.ai/admin/billing-usage/usage-limits>
- Cerebras pricing and Developer credit terms: <https://www.cerebras.ai/pricing>
- NVIDIA NIM Developer Program and API Catalog: <https://docs.api.nvidia.com/nim/docs/product> and <https://docs.api.nvidia.com/nim/docs/api-quickstart>

## Local policy catalog

`workshop/providers/policy.py` implements a fail-closed preflight. The tracked `config/provider-catalog.example.json` is intentionally empty. Copy it to the gitignored `config/provider-catalog.json` only after completing official-source verification. Each model entry requires:

- `enabled: true`, `access_type: free_tier`, and `verification_status: verified`
- valid `verified_at` and future `expires_at` dates
- official HTTPS `source_url` and `terms_url` values (a human must verify source authenticity)
- exact zero input and output token prices
- explicit allowed region codes and maximum input/output tokens per request
- one or more quota windows, each with a metric, positive limit, window in seconds, `account`, `organization`, `project`, or `model` scope, and maximum acceptable snapshot age (optional in the catalog; defaults to at most 300 seconds)

Unknown models, malformed policies, expired entries, non-zero prices, and requests outside listed region, token, or quota limits are denied. The empty example has no model entries, so all model requests are denied by default.

The local policy gate does not make network calls. It also cannot prove that a cited source URL is official, that an account remains on a free tier, or that the account's external quota has not been consumed through another app or device. Those facts require user verification and provider-dashboard reconciliation.

## Local quota ledger

`workshop/providers/usage_ledger.py` maintains request reservations in `.workshop/provider-usage.sqlite3`:

- SQLite transactions use `BEGIN IMMEDIATE` so concurrent local tasks cannot both reserve the last request slot.
- Configured windows are checked before the reservation is inserted. Supported metrics are requests, combined tokens, input tokens, output tokens, and Neurons. Combined tokens counts reserved input plus output tokens against one shared provider limit.
- Account, organization, and project quotas aggregate across models for their independently supplied boundary alias; model-scoped quotas apply only to the exact model ID.
- Every quota window must have a fresh imported external snapshot. The snapshot carries the provider's actual reset time, so the ledger does not guess the reset boundary.
- Reservations are made before network I/O and are not refunded after a timeout or ambiguous failure, because the provider may have processed the request.
- A snapshot establishes the provider-reported baseline. Local reservations created after its capture time are added, while earlier local events are assumed to be included in that baseline. This avoids double-counting, provided the snapshot accurately reflects provider usage at capture time.
- A request is denied when any required snapshot is missing, older than the policy's `snapshot_max_age_seconds`, past its provider reset time, or inconsistent with the model policy's limit.
- Account-scoped snapshots apply across models only when those models use the same provider/account quota limit. Model-scoped snapshots apply only to the exact model.
- Input token counts are caller-supplied conservative estimates (including system instructions and context); the CLI does not tokenize prompts. Maximum output tokens are reserved in advance.
- Any nonzero Neuron request is denied unless the policy defines a Neuron quota window.
- The ledger stores metadata and estimated token/unit counts, never prompts or API keys. `account_scope` is a local label shared by all credentials belonging to the same provider quota boundary (for example, an organization or project); it is not a credential.

`provider reconcile SNAPSHOT.json` imports a validated snapshot created from a provider dashboard/API or a manually recorded rate-limit header. The example format is `config/provider-quota-snapshot.example.json`. A snapshot includes provider/model, non-secret account scope, source URL, source type, capture time, the reported used/limit values, and the provider's exact reset time. The importer rejects credential-like fields, non-HTTPS sources, future captures, unknown quota windows, limit mismatches, and invalid reset times. Partial snapshots are accepted for incremental reconciliation, but a request remains blocked until every quota in its policy has a current matching snapshot.

For a live, read-only refresh, set `OPENROUTER_API_KEY` in the environment and run:

```bash
python3 -m workshop provider refresh-openrouter-key \
  --model "exact/model-id:free" --account-scope openrouter-personal
```

This command performs exactly one authenticated HTTPS GET to `/api/v1/key`, uses the environment variable only, rejects redirects, caps the response at 1 MiB, sanitizes errors, and does not retry. It can use a disabled local policy so quota evidence can be collected before model activation. The policy must define exactly one account-scoped `requests/86400` quota whose limit matches the API response. The command imports only that daily free-model request counter into the quota ledger. It also displays the API-key credit-limit remainder and effective budget remainder returned by the endpoint; those monetary fields are informational and are not represented as quota-ledger metrics or proof that billing is disabled. It does not report the free-model per-minute limit, model/provider-specific limits, or all upstream provider quotas. It does not establish free-tier eligibility. No inference request is made.

For OpenRouter, save the JSON body from the official `GET https://openrouter.ai/api/v1/key` endpoint, then run:

```bash
python3 -m workshop provider reconcile-openrouter-key /tmp/openrouter-key-status.json \
  --model "exact/model-id:free" \
  --account-scope openrouter-personal \
  --captured-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

The converter imports `data.free_model_daily_requests` and calculates its reset at the next 00:00 UTC boundary. The endpoint does not expose every per-minute/model-provider rate limit, so those quotas still need their own dashboard or header snapshot. Do not save an API key or Authorization header in the response file. The converter does not make a network request itself.

For Groq, save only the six documented rate-limit headers from a successful response as a JSON object (do not include Authorization, cookies, API keys, request bodies, or unrelated logs):

```json
{
  "x-ratelimit-limit-requests": "1000",
  "x-ratelimit-remaining-requests": "990",
  "x-ratelimit-reset-requests": "23h59m59s",
  "x-ratelimit-limit-tokens": "12000",
  "x-ratelimit-remaining-tokens": "11800",
  "x-ratelimit-reset-tokens": "52.4s"
}
```

Import the captured headers with:

```bash
python3 -m workshop provider reconcile-groq-headers /tmp/groq-rate-limits.json \
  --model "exact-groq-model-id" --account-scope groq-organization \
  --captured-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

The converter recognizes only account-scoped requests/86400 (RPD) and combined tokens/60 (TPM) policy windows, and it requires each header limit to match the catalog exactly. Reset durations are relative to --captured-at. The ledger counts conservative input-token estimates plus the reserved maximum output tokens against combined tokens. Groq also documents dashboard-only and other dimensions (including separate input/output token limits when configured); those are not inferred from these headers and must be independently reconciled when present in the model policy. The command reads a saved file only and makes no API request. See the official [Groq rate-limit documentation](https://console.groq.com/docs/rate-limits).
Groq documents organization-level rate limits and also supports project-specific per-model overrides. The response headers do not identify the project, and this importer does not reconcile project overrides or separate ITPM/OTPM values. Do not use it as the sole quota evidence if project overrides or separate input/output limits are configured. In that case, keep the model disabled until every applicable organization and project quota can be represented and reconciled. See [Groq Projects](https://console.groq.com/docs/projects) for project rate-limit behavior.

`provider preflight` is read-only: it checks whether one additional request currently fits but does not reserve it. Every adapter must use `execute_with_free_tier_gate` from `workshop/providers/runner.py`, which verifies the model policy, requires fresh snapshots, atomically reserves quota, and only then calls the adapter. Do not call an adapter's raw `complete` method directly.

### OpenRouter adapter

`workshop/providers/openrouter.py` implements non-streaming Chat Completions using `urllib` (no third-party dependency). The CLI entry point is `provider chat MODEL --message TEXT --input-tokens N --max-output-tokens N --region MX --account-scope ALIAS`. Set `OPENROUTER_API_KEY` in the environment; never put it in the catalog or command line. The adapter sends the exact model ID, does not send a `models` fallback list, sets `provider.allow_fallbacks` to `false`, and never retries a request. It returns provider-reported token counts and a request/generation ID when supplied. HTTP errors are classified using the documented `error.metadata.limit_source` and `provider_code` fields, plus safe `Retry-After` and `X-RateLimit-*` values when present. The response body and credentials are never displayed. These diagnostics do not trigger retries or change quota reservations: a failed/ambiguous request remains reserved because the provider may have counted it.

OpenRouter documents a shared free-model cap of 20 requests/minute and a daily cap reported by `GET /api/v1/key`; the free-model collection states failed attempts count against the daily cap. The key endpoint does not report the per-minute counter. On OpenRouter-originated free-model limit errors, the response may include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` (Unix milliseconds). Upstream provider capacity errors are distinct and may carry `metadata.limit_source=upstream_provider_shared_pool` and a `Retry-After` header. The adapter reports these distinctions but does not wait, retry, switch providers, or switch models. See <https://openrouter.ai/docs/api_reference/limits> and <https://openrouter.ai/collections/free-models>.

The adapter does not enable any model. The tracked catalog is empty, and the local catalog must contain a verified `openrouter` policy plus fresh snapshots for every configured quota window before `provider chat` can reach the network. OpenRouter's request and routing controls are documented at <https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request> and <https://openrouter.ai/docs/guides/routing/provider-selection>. Disabling provider fallback can reduce availability; failures are surfaced rather than routed elsewhere.

The ledger and imported snapshots are local to this machine and database file. They do not coordinate other devices or update provider-side quotas. Before enabling an adapter, reconcile every source of usage for that provider account, including external apps and devices, and make sure the local account-scope alias represents the same quota boundary.

## Verification log

| Date | Provider / model | What changed / official source |
| :--- | :--- | :--- |
| 2026-11-22 | OpenRouter adapter | Added standard-library Chat Completions adapter, exact-model requests, provider fallback disabled, no retries, and gated CLI entry point. No model enabled. |
| 2026-11-22 | Groq response headers | Added saved-header conversion for RPD and combined TPM; other account limits still require separate reconciliation. No model enabled. |
| 2026-11-21 | Initial provider review | Added official-source assessment and exclusions/candidates above. No models approved for the local catalog. |


### Quota boundary v2

Policies may define multiple quota entries across four boundary types:

- `account`: legacy `--account-scope` alias, shared across models.
- `organization`: explicit `--quota-scope organization=ORG_ALIAS`, shared across models in that organization.
- `project`: explicit `--quota-scope project=PROJECT_ALIAS`, shared across models in that project.
- `model`: exact model ID; no user-supplied alias is accepted.

For generic snapshot entries, add `scope_id` to organization/project entries. It must match the local alias supplied at reservation time. Do not include credentials in aliases or snapshots. A missing alias or snapshot for any configured quota denies the entire request. Version-1 account/model snapshots remain supported.
