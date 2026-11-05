#!/usr/bin/env bash
# Claude Code PreToolUse hook (matcher: Bash). Wired in .claude/settings.json.
# Enforces CLAUDE.md rules at `git commit` time so they do not depend on the model
# remembering them late in a session:
#   - "pytest must pass before any commit"           (Commands)
#   - nothing under data/ is committed                (Rule 4)
#   - no .env file and no literal CTA_API_KEY value   (Rule 5)
# Reads the hook JSON on stdin; exits 2 to block the command (stderr is shown to
# the model), 0 to allow. Any Bash command that is not a git commit passes through.
set -u

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' 2>/dev/null) || exit 0
case "$cmd" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" || exit 0

fail=0

bad_paths=$(git diff --cached --name-only | grep -E '^data/|(^|/)\.env$' || true)
if [ -n "$bad_paths" ]; then
  echo "Blocked: staged paths under data/ or a .env file (CLAUDE.md rules 4 and 5). Unstage them:" >&2
  echo "$bad_paths" >&2
  fail=1
fi

if git diff --cached -U0 | grep -E '^\+[^+]' | grep -Eq 'CTA_API_KEY[[:space:]]*=[[:space:]]*["'"'"'][^"'"'"']+["'"'"']'; then
  echo "Blocked: a staged line assigns a literal CTA_API_KEY value (CLAUDE.md rule 5). Read it from .env instead." >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  if ! out=$(python -m pytest -q 2>&1); then
    echo "Blocked: pytest failed. CLAUDE.md: all tests must pass before any commit. Fix the failure; do not skip or xfail it to get past this check." >&2
    echo "$out" | tail -40 >&2
    fail=1
  fi
fi

[ "$fail" -eq 0 ] && exit 0
exit 2
