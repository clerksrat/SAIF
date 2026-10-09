#!/usr/bin/env bash
# Usage: ./run_week.sh 7            pull + build, leave docs/ changed locally
#        ./run_week.sh 7 --push     ...and commit + push docs/ and state/ (publishes the site)
set -euo pipefail
cd "$(dirname "$0")"
WEEK="${1:?usage: ./run_week.sh <week> [--push]}"
[ -f .env ] && set -a && . ./.env && set +a      # CFBD_API_KEY, SPORTSDATAIO_API_KEY, ODDS_API_KEY
python3 saif_pull_all.py
python3 build_board.py --week "$WEEK"
if [ "${2:-}" = "--push" ]; then
  git add docs state
  git diff --cached --quiet && { echo "No changes to publish."; exit 0; }
  git commit -m "Week $WEEK board $(date -u +%Y-%m-%dT%H:%MZ)"
  git pull --rebase -q && git push -q
  echo "Published."
fi
echo "Built docs/index.html for week $WEEK"
