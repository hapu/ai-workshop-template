# Decisions

One entry per important decision, newest first. Supersede decisions instead of deleting them.

## 2026-11-22: Reserve provider quotas before network I/O
- **Status:** accepted
- **Decision:** Use SQLite with `BEGIN IMMEDIATE` for local quota reservations. Every future adapter must be invoked through `execute_with_free_tier_gate`, which validates policy and commits quota reservation before calling the adapter.
- **Why:** Parallel tasks must not both consume the last local request slot. An uncertain timeout may still have reached the provider, so reservations are not refunded automatically.
- **Alternatives rejected:** Read-only preflight as the sole gate, in-memory counters, and automatic quota refunds after transport errors.
- **Consequences / follow-up:** The ledger only counts traffic routed through this installation. Reconcile external account usage and dashboard limits before enabling adapters; use one non-secret account/project alias for the same quota scope.

## 2026-11-22: Keep the provider allowlist empty until account limits are verified
- **Status:** accepted
- **Decision:** Do not add enabled provider models based only on public pricing pages. Require account/project quota, region, model, billing, and data-use confirmation before adding a verified policy.
- **Why:** Free access can vary by account, model, region, plan, and external usage. A client-side policy cannot observe all usage outside its local ledger.
- **Alternatives rejected:** Guessing generic limits or enabling a model based only on its advertised free tier.
- **Consequences / follow-up:** Review provider dashboards before enabling the first live adapter.

## 2026-11-21: Start with a standard-library task CLI
- **Status:** accepted
- **Decision:** Use Python 3.10+ and JSON files for the first executable task-management slice. Keep model providers, browser integrations, and Git automation out of this phase.
- **Why:** This is lightweight, testable on the target Chromebook, requires no paid service, and creates a stable task/handoff boundary for later components.
- **Alternatives rejected:** A database, web UI, local model runtime, and multi-agent orchestration in the first iteration.
- **Consequences / follow-up:** Add provider and workflow modules only behind tested interfaces; keep `.workshop/` private and untracked.

## 2026-11-21: Preserve the existing GPL-3.0 license
- **Status:** accepted
- **Decision:** Keep the repository's existing GPL-3.0 `LICENSE` and correct README references to match it.
- **Why:** The license file and GitHub repository metadata both identify GPL-3.0; there was no instruction to relicense the repository.
- **Alternatives rejected:** Replacing the license with Apache-2.0 without an explicit licensing decision.
- **Consequences / follow-up:** Ensure future documentation and template metadata consistently identify GPL-3.0.

## YYYY-MM-DD: Title
- **Status:** proposed / accepted / superseded
- **Decision:**
- **Why:**
- **Alternatives rejected:**
- **Consequences / follow-up:**
