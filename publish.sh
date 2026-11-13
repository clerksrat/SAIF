#!/usr/bin/env bash
# Sync with GitHub and push whatever is already committed. Used by run_week.sh and cbb/run_cbb.py.
#   ./publish.sh sync   -> just pull (start of a run)
#   ./publish.sh        -> pull + push (end of a run)
# Uses a merge that keeps the Pi's own version of any conflicting generated file (docs/, state/),
# so a cloud commit landing mid-run can never leave the repo stuck mid-rebase again
# (what happened Nov 12-13: docs/index.html conflicted and every later run silently failed to push).
cd "$(dirname "$0")"
git rebase --abort 2>/dev/null || true
git merge --abort 2>/dev/null || true
if ! git pull --no-rebase -X ours --no-edit -q; then
  git merge --abort 2>/dev/null || true
  echo "SYNC FAILED: could not pull from GitHub (offline?) -- local commits kept, next run retries"
  exit 1
fi
[ "${1:-}" = "sync" ] && exit 0
if git push -q; then
  echo "Published."
else
  echo "PUBLISH FAILED: push rejected -- local commits kept, next run retries"
  exit 1
fi
