#!/usr/bin/env bash
# Usage:
#   ./run_week.sh monday --push  Monday: pull, grade last week, update performance, build board, publish
#   ./run_week.sh auto --push    Tue-Sat: pull injuries/odds (+ light CFBD refresh), rebuild board, publish
#   ./run_week.sh 7              pull + build a specific week, leave docs/ changed locally
#   ./run_week.sh 7 --push       ...and commit + push docs/ and state/ (publishes the site)
# "auto" and "monday" pick the week from the date: the week of the next Saturday on/after today.
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:?usage: ./run_week.sh <monday|auto|week> [--push]}"
if [ "$MODE" = "auto" ] || [ "$MODE" = "monday" ]; then   # 2026 Week 1 = Sat Sep 5
  WEEK=$(python3 -c "import math,datetime as d;print(math.ceil((d.date.today()-d.date(2026,9,5)).days/7)+1)")
else
  WEEK="$MODE"
fi
[ -f .env ] && set -a && . ./.env && set +a      # CFBD_API_KEY, SPORTSDATAIO_API_KEY, ODDS_API_KEY
if [ "${2:-}" = "--push" ]; then                  # build with the latest template/scripts from GitHub
  git pull --rebase --autostash -q || echo "WARNING: git pull failed; building with the local copy"
fi
echo "=== $(date '+%a %Y-%m-%d %H:%M %Z')  mode=$MODE  week=$WEEK ==="

python3 saif_pull_all.py --week "$WEEK"

if [ "$MODE" = "monday" ]; then
  PREV=$((WEEK - 1))
  if [ -f "state/week${PREV}_scored.pkl" ]; then
    python3 grade_week.py "$PREV"   || echo "WARNING: grading week $PREV failed -- performance not updated"
    python3 update_performance.py   || echo "WARNING: performance update failed"
  else
    echo "No board saved for week $PREV -- nothing to grade"
  fi
fi

python3 build_board.py --week "$WEEK"

if [ "${2:-}" = "--push" ]; then
  git add docs state
  git diff --cached --quiet && { echo "No changes to publish."; exit 0; }
  git commit -q -m "Week $WEEK $MODE $(date -u +%Y-%m-%dT%H:%MZ)"
  git pull --rebase --autostash -q && git push -q
  echo "Published."
fi
echo "Built docs/index.html for week $WEEK"
