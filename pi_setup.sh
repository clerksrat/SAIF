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
bash install_cron.sh   # Mon grade+publish, Tue-Sat board, closing-line snapshots
echo "Test now with:  . .venv/bin/activate && ./run_week.sh auto      (no --push)"
