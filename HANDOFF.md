# Handoff

Keep under 300 words. Refresh at the end of each work session.

- **Date:** 2026-11-24
- **Repository:** `hapu/ai-workshop-template` (master template; GPL-3.0).
- **Stable branch:** `main`; reviewed head: `574ef89c70b9d8d4c307efac76af9a66aa9bf4eb`. Work on feature branches and use PRs.
- **CI:** Main promotion PR #26 passed the required CI workflow on Python 3.10–3.13 (run [#158](https://github.com/hapu/ai-workshop-template/actions/runs/45327477908)).
- **Implemented:** Standard-library task/checkpoint persistence, bounded project context and handoffs, provider policy/quota ledger, gated OpenRouter adapter, proposal staging/preview, and POSIX proposal apply/recovery.
- **Proposal safety:** Apply requires a full staged-record SHA-256 and exact interactive confirmation. Recovery requires a separate journal-digest-bound confirmation. Interrupted transactions roll back by default; committed transactions allow cleanup only. Multi-file application is recoverable, not globally atomic to external observers.
- **Safety boundaries:** No proposal content is executed. Apply/recovery do not invoke providers, install packages, run shell commands, or perform Git writes. The provider catalog remains empty by default.
- **Next task:** Validate the template on the SAT XML Manager pilot. Record setup friction, missing context, handoff gaps, and any proposal/recovery issues before expanding automation.
- **Local checks:** `python3 -m unittest discover -s tests/unit -v`; `bash scripts/check-words.sh`; `bash tests/smoke.sh`.
- **Start:** `git switch main && git pull --ff-only`; check `git status --short --branch`; create a fresh feature branch. Do not work directly on `main`.
