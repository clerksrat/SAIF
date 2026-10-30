#!/usr/bin/env bash
# Install (or replace) the SAIF schedule on the Pi. Run from inside the repo:  bash install_cron.sh
#   Mon 9:00       monday mode: pull, grade last week, update performance, build + publish board
#   Tue-Fri 9:00   daily: injuries + odds (+ light CFBD refresh), rebuild + publish board
#   Sat 8:00       daily, earlier for noon kickoffs
#   every 30 min 11:00-23:30   closing-line snapshot (only calls the API when a game kicks off within 35 min)
# All times America/New_York.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
chmod +x run_week.sh
BASE="cd $PWD && . .venv/bin/activate"
( crontab -l 2>/dev/null | grep -v -e 'run_week.sh' -e 'snapshot_close.py' -e '^CRON_TZ=' || true ;
  echo "CRON_TZ=America/New_York"
  echo "0 9 * * 1 $BASE && ./run_week.sh monday --push >> logs/run.log 2>&1"
  echo "0 9 * * 2-5 $BASE && ./run_week.sh auto --push >> logs/run.log 2>&1"
  echo "0 8 * * 6 $BASE && ./run_week.sh auto --push >> logs/run.log 2>&1"
  echo "*/30 11-23 * * * $BASE && python3 snapshot_close.py >> logs/close.log 2>&1" ) | crontab -
echo "Cron installed:"
crontab -l
