# SAIF — Sports Alternative Investment Fund

Weekly CFB research board: frozen **Alpha** ridge-10 model and **Beta** (Alpha + signed tier_gap), scored against the market, published as a static site from `docs/`.

## Run it (Raspberry Pi or any machine)

    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    cp .env.example .env            # add CFBD / SportsDataIO / Odds API keys (never commit .env)
    ./run_week.sh 7 --push          # pull, score, build docs/, commit + push

On the Pi, `bash install_cron.sh` sets the schedule (times ET):
- **Mon 9:00** `./run_week.sh monday --push`: pull, grade last week, update `docs/live.json`, build + publish the board
- **Tue–Fri 9:00, Sat 8:00** `./run_week.sh auto --push`: injuries + odds (+ a 2–5 call CFBD refresh), rebuild + publish
- **Every 30 min, 11:00–23:30** `snapshot_close.py`: closing-line snapshot for CLV; only calls The Odds API (1 credit, spreads only) when a game kicks off within 35 min

Logs: `logs/run.log`, `logs/close.log`.

## Layout
- `saif_pull_all.py` — one pull: CFBD collector + SportsDataIO injuries + The Odds API (refetches only live 2026 data)
- `snapshot_close.py` — closing-line snapshots → `state/closing_lines.csv`
- `install_cron.sh` — the Pi schedule
- `cfb_collect_fullseason.py` — the CFBD collector (unchanged)
- `build_board.py` — scores the week, builds `docs/index.html` (margin breakdowns, injuries, line moves, finals)
- `models/` — `fitted_model.json` (Alpha, exact), `beta_model.json` (Beta, reconstructed from spec), conference map, backtest summary
- `assets/` — page template + logo
- `docs/` — published site (`index.html` live board, `performance.html` tracking page)
- `state/` — last build per week, so "moved from" lines persist across rebuilds

## Publishing
Settings → Pages → Deploy from branch → `main` / `/docs`. (Free for public repos; private repos need a paid plan.)

## Notes
- CFBD cache: prior seasons are pulled once and kept forever. For 2026 only the schedule and not-yet-final weeks are refetched (a finished week's stats are kept once pulled 24h after its last kickoff), and features are built only through the board week. A normal run is 2–5 CFBD calls (was ~41). To force a full refresh (e.g. offseason stat corrections), delete `cfb_fullseason_data_2026/raw/`.
- Lines: the board uses The Odds API consensus across US books (`odds_lines.py`), falling back to CFBD per game; cards show the best number available.
- Grading is automatic on Mondays. By hand: `python grade_week.py N`, `python update_performance.py`.
- CLV: `state/closing_lines.csv` holds the pre-kick snapshots; `grade_week.py` adds `close_spread_home` and `alpha_clv`/`beta_clv` (points vs the close for the side picked) and prints avg CLV and % beating the close.
- Research tool, not betting advice. Injuries are display-only and not in either model.
