# SAIF — Sports Alternative Investment Fund

Weekly CFB research board: frozen **Alpha** ridge-10 model and **Beta** (Alpha + signed tier_gap), scored against the market, published as a static site from `docs/`.

## Run it (Raspberry Pi or any machine)

    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    cp .env.example .env            # add CFBD / SportsDataIO / Odds API keys (never commit .env)
    ./run_week.sh 7 --push          # pull, score, build docs/, commit + push

On the Pi, `bash install_cron.sh` sets the schedule (times ET):
- **Sun 21:00** `./run_week.sh auto --push`: first look at next week's lines; SAIF entries lock here
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

## SAIF play policy (from Week 11, `saif_policy.py`)
- Board edge = 0.15 x Alpha's gap to the line (shrunk). A play = shrunk edge >= 1.0 at the entry line, flat 1 unit.
- Entry = the first consensus (Odds API) line the board sees for a game; locked once in `state/cfb_entries.csv` with a timestamp and best-book numbers. Never re-decided.
- Three result sets, never mixed: consensus benchmark (every signal play at the consensus entry number, -110; not executable), paper tickets (an observed FanDuel / DraftKings / BetRivers quote: fresh <= 90 min at the pull, price within -125..+115, best number then best price), and placed bets (fill `placed_book/point/price` in `state/cfb_entries.csv` by hand). A signal with no qualifying quote is "no executable entry" and stays out of executable results and CLV.
- Both gaps are logged: model vs the consensus line (`consensus_raw_gap`) and model vs the ticket number (`ticket_raw_gap`).
- `snapshot_close.py` also writes every book's closing quote (both sides, point and price, book timestamp) to `state/closing_quotes.csv`. Alternate lines at the ticket's exact number are not captured.
- QB1 is judged only with what was known at entry: a pick on a team already flagged STALE is skipped (logged with what it would have done). QB news after entry does not void the bet; it is flagged (`saif_qb_news`).
- Beta is a shadow model: shown and graded, never a play.
- `grade_week.py` grades SAIF plays at the locked ticket (`saif_*` columns, `saif` row in summary.csv) and logs, for every locked game, whether the line moved toward the model after entry (`entry_move_model`, `entry_clv_model`).

## Notes
- CFBD cache: prior seasons are pulled once and kept forever. For 2026 only the schedule and not-yet-final weeks are refetched (a finished week's stats are kept once pulled 24h after its last kickoff), and features are built only through the board week. A normal run is 2–5 CFBD calls (was ~41). To force a full refresh (e.g. offseason stat corrections), delete `cfb_fullseason_data_2026/raw/`.
- Lines: the board uses The Odds API consensus across US books (`odds_lines.py`), falling back to CFBD per game; cards show the best number available.
- Grading is automatic on Mondays. By hand: `python grade_week.py N`, `python update_performance.py`.
- CLV: `state/closing_lines.csv` holds the pre-kick snapshots; `grade_week.py` adds `close_spread_home` and `alpha_clv`/`beta_clv` (points vs the close for the side picked) and prints avg CLV and % beating the close.
- Research tool, not betting advice. Injuries are display-only and not in either model.

## College basketball (dry run)
- `cbb/run_cbb.py --push` — daily 10:15 ET on the Pi: tops up 2027 CBBD data, refits ratings, logs a morning entry line per game (`cbb/state/entries.csv`), grades finals vs CBBD's closing line with CLV (`cbb/state/graded.csv`), publishes `docs/cbb.html`. Paper only.
- `cbb/ratings.py` — efficiency + tempo ratings; `SIDES` and `TOTALS` are the production settings. `build_priors(season)` once a year.
- `cbb/backtest.py` (sides) and `cbb/totals_backtest.py` — walk-forward backtests with tuning; reports in `cbb/*_report.md`. `cbb/backtest_summary.py` writes `cbb/models/backtest_summary.json`, the numbers shown on the page (rerun after changing settings).
- Live results log: `cbb/state/entries.csv` (every game at its morning line) and `cbb/state/graded.csv` (results + CLV), committed daily by the Pi.
- `cbb/backfill_cbbd.py` — CBBD history by date window (the API caps responses at 3,000 rows). One gzipped file per season in `cbb/data/`.
- Unmapped Odds API team names print in `logs/cbb.log`; add them to `cbb/odds_match.py`.
