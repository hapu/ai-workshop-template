# Handoff

Keep under 300 words. Overwrite each session.

- **Date / device / assistant:** 2026-11-22; Python 3.10+ standard-library implementation.
- **Branch / base:** `feature/openrouter-rate-limit-diagnostics`, based on main `721035a2a82c19e914196a6d1536642a39987a02`.
- **Current PR:** #11 — https://github.com/hapu/ai-workshop-template/pull/11
- **Done:** Verified PR #10 merged. Added bounded parsing of OpenRouter HTTP error metadata and documented rate-limit headers. The adapter now exposes safe status, limit source, upstream provider code, Retry-After, and X-RateLimit values without printing response bodies or credentials. Added mocked tests for OpenRouter free-tier and upstream 429 classification and malformed headers. Updated provider docs, roadmap, decisions, TODO, and development log.
- **Checks:** CI run [45067447134](https://github.com/hapu/ai-workshop-template/actions/runs/45067447134) passed on Python 3.10–3.13; 110 unit tests, word-budget checks, and repository smoke tests passed.
- **Limitations:** No retries, cooldown persistence, provider/model fallback, live request, or model activation. Key-status endpoint still does not expose per-minute quota proactively. Account-level quota, external usage, region, and billing safeguards remain unverified.
- **Next step:** Review PR #11; merge only after explicit user approval. Keep the tracked provider catalog empty.
- **Do not delete / assumptions:** Never send credentials in chat or commit secrets. Failed/ambiguous reservations remain charged locally.
