#!/usr/bin/env bash
# One-time setup on the Raspberry Pi (Raspberry Pi OS / Debian). Run from inside the cloned repo:
#   bash pi_setup.sh
set -euo pipefail
cd "$(dirname "$0")"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip git
python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
chmod +x run_week.sh
[ -f .env ] || { cp .env.example .env; echo ">> Edit .env and paste your three keys:  nano .env"; }
git config user.name  "SAIF Pi"
git config user.email "saif-pi@users.noreply.github.com"
mkdir -p logs
CRON_TZ_LINE="CRON_TZ=America/New_York"
JOB="cd $PWD && . .venv/bin/activate && ./run_week.sh auto --push >> logs/run.log 2>&1"
# Tue 9:00 (new lines), Thu 9:00 (mid-week moves), Sat 8:00 (final pre-kick lines/results)
( crontab -l 2>/dev/null | grep -v 'run_week.sh' | grep -v '^CRON_TZ=' ;
  echo "$CRON_TZ_LINE"
  echo "0 9 * * 2,4 $JOB"
  echo "0 8 * * 6 $JOB" ) | crontab -
echo "Cron installed:"; crontab -l
echo "Test now with:  . .venv/bin/activate && ./run_week.sh auto      (no --push)"
