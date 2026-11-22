#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

fail=0
ok() { echo "ok    $1"; }
bad() { echo "FAIL  $1"; fail=1; }

required=(
  README.md
  WORKSHOP.md
  AGENTS.md
  PROJECT_CONTEXT.md
  HANDOFF.md
  TODO.md
  DECISIONS.md
  DEVELOPMENT_LOG.md
  LICENSE
  docs/ARCHITECTURE.md
  docs/NEW_PROJECT.md
  docs/PROVIDERS.md
  docs/ROADMAP.md
  docs/SECURITY.md
  docs/WORKFLOW.md
  config/examples/env.example
  scripts/check-words.sh
  tests/smoke.sh
  workshop/__init__.py
  workshop/__main__.py
  workshop/cli.py
  workshop/models.py
  workshop/task_store.py
  workshop/handoff.py
  tests/unit/test_task_store.py
)

for path in "${required[@]}"; do
  if [ -s "$path" ]; then ok "$path"; else bad "$path (missing or empty)"; fi
done

if bash scripts/check-words.sh; then ok "word budgets"; else bad "word budgets"; fi

if git rev-parse --git-dir >/dev/null 2>&1; then
  secrets="$(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -vE '(^|/)\.env\.example$' || true)"
  if [ -z "$secrets" ]; then ok "no tracked .env files"; else
    echo "FAIL  tracked .env files:"; echo "$secrets"; fail=1
  fi
else
  echo "skip  git checks (not a git repo)"
fi

for script in scripts/*.sh tests/*.sh; do
  [ -f "$script" ] || continue
  if bash -n "$script"; then ok "$script syntax"; else bad "$script syntax"; fi
done

if command -v python3 >/dev/null 2>&1; then
  if python3 -m workshop --version >/dev/null; then ok "CLI starts"; else bad "CLI starts"; fi
  if python3 -m unittest discover -s tests/unit -v; then ok "Python unit tests"; else bad "Python unit tests"; fi
  if python3 - <<'PY'
from pathlib import Path
import re
import sys

files = [Path("README.md"), Path("WORKSHOP.md"), Path("AGENTS.md"), *Path("docs").glob("*.md")]
bad = []
for path in files:
    if not path.is_file():
        continue
    content = path.read_text(encoding="utf-8")
    for match in re.finditer(r"\]\(([^)]+)\)", content):
        target = match.group(1).strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if not (path.parent / target).resolve().exists():
            bad.append(f"{path}: {target}")
if bad:
    print("FAIL  local Markdown links:")
    print("\n".join(bad))
    sys.exit(1)
print("ok    local Markdown links")
PY
  then :; else fail=1; fi
else
  echo "skip  Python checks (python3 not found)"
fi

exit "$fail"
