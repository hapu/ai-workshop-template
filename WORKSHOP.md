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
7. **Reproducible:** record setup steps, versions, and exact test results.

## 2. Devices

**Chromebook** (Celeron N4500, 4 GB RAM, ~15 GB Linux storage): editing, Git, terminal, scripts, and lightweight tests.
- Use lightweight tools such as `vim`, `nano`, `micro`, `git`, and Python.
- Avoid Docker, local LLMs, heavy IDEs, and large databases.
- Keep browser tabs few; ChromeOS may stop the Linux container when memory runs out.

**Android phone:** read and edit docs, review diffs, Termux + SSH, and browser-based coding assistants.

## 3. Local task and context CLI

The starter runtime is dependency-free Python 3.10+ and manages task state, resumable checkpoints, bounded project context, and portable assistant handoffs:

```bash
python3 -m workshop doctor
python3 -m workshop task create "Implement feature" --description "Goal and acceptance criteria"
python3 -m workshop task checkpoint add TASK_ID "Inspect code"
python3 -m workshop task checkpoint list TASK_ID
python3 -m workshop task checkpoint complete TASK_ID CHECKPOINT_ID
python3 -m workshop task resume TASK_ID
python3 -m workshop task handoff TASK_ID --output .workshop/handoff.md
python3 -m workshop context build --project . --max-words 2500 --output .workshop/context.md
```

Task data lives under `.workshop/` and is ignored by Git. The context builder reads an allowlist of six project context files, enforces per-file and aggregate word budgets, and rejects symlinks that resolve outside the project root. The CLI makes no network requests and does not call an AI model.

## 4. Providers and gateways

Provider limits and model names change. Track them in `docs/PROVIDERS.md` with a last-verified date and official source. Never assume a free tier is permanent.

- **OpenRouter** (optional): one endpoint for multiple models; check each model's free-tier conditions.
- **LiteLLM** (optional): routing and fallbacks; it does not provide additional free quota.
- Start with one verified provider and no gateway. Add a gateway only to solve a measured problem.

Do not implement provider requests until the common interface and fail-closed spending gate are tested.

## 5. Coding agent and browser workflow

OpenCode is a candidate coding agent, not a required dependency. Verify installation steps and provider support before relying on it. Browser assistants should receive generated task and context handoffs and return reviewable results; they must not become an undocumented source of project state.

## 6. Repository layout

```text
ai-workshop-template/
├── workshop/              local task, context, and handoff CLI
├── tests/unit/             Python unit tests
├── scripts/                word-budget check
├── tests/                  repository smoke checks
├── config/examples/        variable names only; no real secrets
├── docs/                   architecture, workflow, providers, security, roadmap
├── README.md               template and runtime quick start
├── WORKSHOP.md             this master spec
├── AGENTS.md               rules for AI agents
├── PROJECT_CONTEXT.md      project goal, scope, constraints, status
├── HANDOFF.md              state for the next session or assistant
├── TODO.md                 prioritized tasks
├── DEVELOPMENT_LOG.md      changes and experiments
└── DECISIONS.md            decisions and rationale
```

`main` is stable. Use short-lived `feature/<name>` or `fix/<name>` branches. Review diffs before merging. Do not commit directly to `main`.

## 7. Context budget

Free-tier APIs can have tight input limits, so context files stay concise. The context builder enforces these per-file maximums:

| File | Max words |
| :--- | ---: |
| AGENTS.md | 500 |
| PROJECT_CONTEXT.md | 800 |
| HANDOFF.md | 300 |
| TODO.md | 500 |
| docs/ARCHITECTURE.md | 600 |
| docs/WORKFLOW.md | 800 |

The default aggregate budget is 2,500 words. Raise it explicitly only when the selected model's context capacity and cost policy are verified.

## 8. Development workflow

- **Start:** inspect branch and working tree; read `AGENTS.md`, `PROJECT_CONTEXT.md`, `HANDOFF.md`, `TODO.md`, and `docs/WORKFLOW.md`; resume an existing task or create one.
- **During:** update task checkpoints and notes as work progresses; make one reviewable change at a time; run unit tests and repository checks.
- **End:** export a task handoff, review `git diff`, and record test results. Commit and push only when explicitly requested.

## 9. Security and spending

- Never commit keys, tokens, passwords, or `.env` files.
- Treat `.workshop/` task descriptions, context bundles, and handoffs as private project data.
- No paid usage without explicit approval.
- A future provider router must reject unknown pricing or free-tier eligibility before making a request.
- Follow provider terms; do not evade quotas with extra accounts.

## 10. Roadmap and template maintenance

See `docs/ROADMAP.md` for implementation phases and `docs/PROVIDERS.md` for the verification protocol. Keep this master repository generic. Project-specific goals, context, and tasks belong in each repository created from the template.
