# AI Development Workshop

A portable, provider-agnostic setup for building software with AI assistants from an Android phone and a low-power Chromebook. This repository is a **GitHub template**: create a clean copy for each new project and keep this master repository generic.

This is the master spec. Keep it under 2,000 words (`scripts/check-words.sh` checks).

## 1. Principles

1. **Provider agnostic:** no single provider or model is required.
2. **Free-first, honestly labeled:** separate permanent free quotas from trials and promotional credits.
3. **Git is the source of truth:** code, decisions, and handoff notes live in the repo, not only in chats.
4. **Short, current context:** every assistant gets concise, version-controlled instructions.
5. **Cloud inference, light local tools:** do not require a local LLM.
6. **Human control:** spending, credentials, destructive actions, and publication require approval.
7. **Fail closed:** if free-tier eligibility, current pricing, region access, or terms are unknown, reject the request.
8. **Reproducible:** record setup steps, versions, and exact test results.

## 2. Devices

**Chromebook** (Celeron N4500, 4 GB RAM, ~15 GB Linux storage): editing, Git, terminal, scripts, and lightweight tests.
- Use lightweight tools such as `vim`, `nano`, `micro`, `git`, and Python.
- Avoid Docker, local LLMs, heavy IDEs, and large databases.
- Keep browser tabs few; ChromeOS may stop the Linux container when memory runs out.

**Android phone:** read and edit docs, review diffs, Termux + SSH, and browser-based coding assistants.

## 3. Local task and context CLI

The dependency-free Python 3.10+ runtime manages task state, resumable checkpoints, bounded project context, and portable handoffs:

```bash
python3 -m workshop task create "Implement feature"
python3 -m workshop task checkpoint add TASK_ID "Inspect code"
python3 -m workshop task checkpoint complete TASK_ID CHECKPOINT_ID
python3 -m workshop task resume TASK_ID
python3 -m workshop task handoff TASK_ID --output .workshop/handoff.md
python3 -m workshop context build --project . --max-words 2500 --output .workshop/context.md
```

Task data lives under `.workshop/` and is ignored by Git. The context builder reads an allowlist of six project context files, enforces per-file and aggregate word budgets, and rejects symlinks that resolve outside the project root.

## 4. Provider contracts and zero-cost policy

`workshop/providers/base.py` defines the adapter contract. `workshop/providers/policy.py` loads an explicit local model catalog and performs a fail-closed preflight. No actual inference adapters are included and the default catalog is empty.

Before adding a model policy, verify official pricing, whether access is genuinely free rather than trial/credits, eligible regions and account types, current model limits, and terms. Include verification and expiry dates and official HTTPS source links. The policy gate checks the HTTPS scheme, but a person must verify that the links are official and the policy fields reflect the provider's current terms. The gate rejects any unknown, unverified, expired, non-zero-priced, disabled, region-ineligible, or over-limit model.

Do not bypass the gate in a future provider adapter. A preflight approval does not guarantee provider-side availability and does not replace account spending limits or free-quota usage accounting. Add those controls before enabling live adapters.

## 5. Coding agent and browser workflow

OpenCode is a candidate coding agent, not a required dependency. Browser assistants should receive generated task and context handoffs and return reviewable results; they must not become an undocumented source of project state.

## 6. Context budgets

| File | Max words |
| :--- | ---: |
| AGENTS.md | 500 |
| PROJECT_CONTEXT.md | 800 |
| HANDOFF.md | 300 |
| TODO.md | 500 |
| docs/ARCHITECTURE.md | 600 |
| docs/WORKFLOW.md | 800 |

The default aggregate context budget is 2,500 words. Raise it explicitly only after confirming model context capacity and cost policy.

## 7. Development workflow

- **Start:** inspect branch and working tree; read project context; resume an existing task or create one.
- **During:** update task checkpoints and notes; make one reviewable change at a time; run unit tests and repository checks.
- **Before inference:** run the provider preflight with the correct region and estimates. If it denies, do not try another model unless that model has its own verified policy.
- **End:** export a task handoff, review `git diff`, and record exact test results. Commit and push only when explicitly requested.

## 8. Security and spending

- Never commit API keys, tokens, passwords, or `.env` files.
- Treat `.workshop/` task descriptions, context bundles, and handoffs as private project data.
- Keep `config/provider-catalog.json` local; only the empty example is tracked.
- No paid usage without explicit approval. Unknown prices or eligibility must fail closed.
- Follow provider terms; do not evade quotas with extra accounts.

## 9. Roadmap and template maintenance

See `docs/ROADMAP.md` for implementation phases and `docs/PROVIDERS.md` for the verification protocol. Keep this master repository generic. Project-specific goals, context, and tasks belong in each repository created from the template.
