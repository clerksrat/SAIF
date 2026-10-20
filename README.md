# SAIF — Sports Alternative Investment Fund

Weekly CFB research board: frozen **Alpha** ridge-10 model and **Beta** (Alpha + signed tier_gap), scored against the market, published as a static site from `docs/`.

## Run it (Raspberry Pi or any machine)

    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    cp .env.example .env            # add CFBD / SportsDataIO / Odds API keys (never commit .env)
    ./run_week.sh 7 --push          # pull, score, build docs/, commit + push

Schedule it with cron, e.g. `0 7 * * 2,4,5 cd ~/SAIF && ./run_week.sh 7 --push >> run.log 2>&1` (week number changes weekly).

## Layout
- `saif_pull_all.py` — one pull: CFBD collector + SportsDataIO injuries + The Odds API (clears the stale 2026 cache first)
- `cfb_collect_fullseason.py` — the CFBD collector (unchanged)
- `build_board.py` — scores the week, builds `docs/index.html` (margin breakdowns, injuries, line moves, finals)
- `models/` — `fitted_model.json` (Alpha, exact), `beta_model.json` (Beta, reconstructed from spec), conference map, backtest summary
- `assets/` — page template + logo
- `docs/` — published site (`index.html` live board, `performance.html` tracking page)
- `state/` — last build per week, so "moved from" lines persist across rebuilds

## Publishing
Settings → Pages → Deploy from branch → `main` / `/docs`. (Free for public repos; private repos need a paid plan.)

## Notes
- First pull needs 2022–2025 history; keep `cfb_expanded_data/` beside the scripts if you have it, otherwise the first run re-downloads it.
- Lines: the board uses The Odds API consensus across US books (`odds_lines.py`), falling back to CFBD per game; cards show the best number available.
- After games finish: `python grade_week.py N`, `python update_performance.py`, then upload `docs/live.json`.
- Research tool, not betting advice. Injuries are display-only and not in either model.
