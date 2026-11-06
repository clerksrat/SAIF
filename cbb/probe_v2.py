"""CBB probe v2: line-coverage audit 2014-2027 + a field/depth check of the unused CBBD endpoints.

Run on the Pi from the repo folder:
    . .venv/bin/activate && python3 cbb/probe_v2.py --push

Read-only with respect to the model: it writes nothing under cbb/data, cbb/state or docs.
Outputs cbb/probe_v2_report.txt and cbb/probe_v2.json (committed with --push).

Cost: about 15-17 calls per new season 2014-2021 (games + lines in 28-day windows, split if
near the 3,000-row cap) plus ~20 sample calls, so ~150 total. Seasons 2022-2027 are already
cached (0-3 calls). Every response is cached in cbb_data/raw/ with the backfill's own cache
keys, so a later backfill of 2014-2021 reuses them for free.

Part 1 -- lines, per season x provider (D1-vs-D1 finals only):
  coverage of spread / opener / total / total opener / moneyline;
  open == close share and mean |close - open| (stale or never-updated quotes);
  MAE of open and of close vs the final margin (a real pregame close should beat its open,
  and neither should be suspiciously accurate -- that would signal post-game contamination);
  push rate; agreement with the other books on the same game.
  CBBD line objects carry no timestamps -- the report confirms the field list.
Part 2 -- unused endpoints: rows returned, field names, and depth (2015 vs 2026) where relevant.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import backfill_cbbd as B  # noqa: E402  (same cache, same windows, same retries)

REPORT = HERE / 'probe_v2_report.txt'
JSON_OUT = HERE / 'probe_v2.json'
LOG = []
OUT = {'run_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'lines': {}, 'endpoints': {}}


def say(s=''):
    print(s, flush=True)
    LOG.append(s)


# ---------------------------------------------------------------- part 1: lines audit
def season_tables(season, today):
    g = pd.DataFrame([B.game_row(x) for x in B.pull_season('/games', season, today)])
    raw_lines = B.pull_season('/lines', season, today)
    l = pd.DataFrame([r for x in raw_lines for r in B.line_rows(x)])
    fields = sorted({k for x in raw_lines for ln in (x.get('lines') or []) for k in ln})
    return (B.dedupe(g, ['id']) if len(g) else g, B.dedupe(l, ['game_id', 'provider']) if len(l) else l, fields)


def audit_season(season, today):
    g, l, fields = season_tables(season, today)
    if g.empty:
        say(f'{season}: no games returned')
        return
    d1 = g[g.homeConference.notna() & g.awayConference.notna() & (g.status == 'final')].copy()
    d1['margin'] = d1.homePoints - d1.awayPoints
    d1['total'] = d1.homePoints + d1.awayPoints
    n = len(d1)
    res = {'d1_finals': n, 'line_fields': fields, 'providers': {}}
    if l.empty:
        say(f'{season}: {n} D1 finals | NO LINES')
        OUT['lines'][season] = res
        return
    m = l.merge(d1[['id', 'margin', 'total']], left_on='game_id', right_on='id')
    any_line = m[m.spread.notna()].game_id.nunique()
    any_open = m[m.spreadOpen.notna()].game_id.nunique() if 'spreadOpen' in m else 0
    res.update(games_with_spread=int(any_line), games_with_open=int(any_open))
    say(f'{season}: {n} D1 finals | spread on {any_line} ({any_line / n:.0%}) | opener on {any_open} ({any_open / n:.0%})')
    # consensus of the OTHER books per game, to measure each book's disagreement
    for prov, x in m.groupby('provider'):
        s = x[x.spread.notna()]
        if s.empty:
            continue
        others = m[(m.provider != prov) & m.spread.notna()].groupby('game_id').spread.median()
        agree = (s.set_index('game_id').spread - others).dropna().abs()
        o = s[s.spreadOpen.notna()] if 'spreadOpen' in s else s.iloc[:0]
        t = x[x.overUnder.notna()] if 'overUnder' in x else x.iloc[:0]
        to = x[x.overUnderOpen.notna()] if 'overUnderOpen' in x else x.iloc[:0]
        r = {
            'games': int(len(s)), 'coverage': round(len(s) / n, 3),
            'with_open': int(len(o)), 'with_total': int(len(t)), 'with_total_open': int(len(to)),
            'with_ml': int(x.homeMoneyline.notna().sum()) if 'homeMoneyline' in x else 0,
            'mae_close': round(float((s.margin + s.spread).abs().mean()), 2),
            'push_rate': round(float(((s.margin + s.spread) == 0).mean()), 3),
            'mae_open': round(float((o.margin + o.spreadOpen).abs().mean()), 2) if len(o) else None,
            'open_eq_close': round(float((o.spreadOpen == o.spread).mean()), 3) if len(o) else None,
            'mean_move': round(float((o.spread - o.spreadOpen).abs().mean()), 2) if len(o) else None,
            'total_mae_close': round(float((t.total - t.overUnder).abs().mean()), 2) if len(t) else None,
            'total_mae_open': round(float((to.total - to.overUnderOpen).abs().mean()), 2) if len(to) else None,
            'vs_other_books_mad': round(float(agree.mean()), 2) if len(agree) else None,
            'vs_other_books_n': int(len(agree)),
        }
        res['providers'][prov] = r
        say(f'    {prov:13s} {r["games"]:5d} ({r["coverage"]:.0%}) | open {r["with_open"]:5d} | tot {r["with_total"]:5d} '
            f'| totOpen {r["with_total_open"]:5d} | ML {r["with_ml"]:5d} | MAE close {r["mae_close"]} open {r["mae_open"]} '
            f'| open==close {r["open_eq_close"]} | move {r["mean_move"]} | vs other books {r["vs_other_books_mad"]} '
            f'(n={r["vs_other_books_n"]}) | push {r["push_rate"]}')
    OUT['lines'][season] = res


# ---------------------------------------------------------------- part 2: endpoint samples
def shape(data):
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return {'rows': 0}
    top, nested = Counter(), {}
    for row in data[:200]:
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            top[k] += 1
            if isinstance(v, dict):
                nested.setdefault(k, set()).update(v.keys())
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                nested.setdefault(k + '[]', set()).update(v[0].keys())
    return {'rows': len(data), 'fields': sorted(top), 'nested': {k: sorted(v) for k, v in nested.items()}}


def sample(label, endpoint, params):
    try:
        data = B.get(endpoint, params, datetime(2026, 4, 1, tzinfo=timezone.utc))
        s = shape(data)
        # nested player/stat lists one level deeper (e.g. players[].stats)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            for k, v in data[0].items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    s['nested_rows_' + k] = sum(len(r.get(k) or []) for r in data if isinstance(r, dict))
                    deeper = {kk: sorted(vv.keys()) for kk, vv in v[0].items() if isinstance(vv, dict)}
                    if deeper:
                        s['nested2_' + k] = deeper
    except SystemExit as e:
        s = {'error': str(e)}
    OUT['endpoints'][label] = {'endpoint': endpoint, 'params': params, **s}
    if 'error' in s:
        say(f'  {label:34s} ERROR {s["error"]}')
    else:
        say(f'  {label:34s} rows {s["rows"]:5d} | fields {s.get("fields", [])}')
        for k, v in s.get('nested', {}).items():
            say(f'  {"":34s}   {k}: {v}')
        for k, v in s.items():
            if k.startswith('nested_rows_'):
                say(f'  {"":34s}   {k[12:]} rows: {v}')
            if k.startswith('nested2_'):
                for kk, vv in v.items():
                    say(f'  {"":34s}   {k[8:]}.{kk}: {vv}')


def pick_game(season, conf='ACC'):
    f = HERE / 'data' / f'games_{season}.csv.gz'
    if f.exists():
        g = pd.read_csv(f)
    else:
        g = pd.DataFrame([B.game_row(x) for x in B.pull_window('/games', season, date(season, 1, 10), date(season, 1, 17))])
    g = g[(g.status == 'final') & (g.homeConference == conf) & (g.awayConference == conf)]
    g = g[g.startDate.str[5:7] == '01'] if len(g) else g
    return int(g.iloc[0].id) if len(g) else None


def endpoints():
    say('\n=== Part 2: unused endpoints ===')
    day = {'startDateRange': '2026-01-10T00:00:00Z', 'endDateRange': '2026-01-11T00:00:00Z'}
    day15 = {'startDateRange': '2015-01-10T00:00:00Z', 'endDateRange': '2015-01-11T00:00:00Z'}
    g26, g15 = pick_game(2026), pick_game(2015)
    say(f'  sample games: 2026 id {g26}, 2015 id {g15}')
    sample('player box 2026 (1 day)', '/games/players', {'season': 2026, **day})
    sample('player box 2015 (1 day)', '/games/players', {'season': 2015, **day15})
    sample('roster Duke 2027', '/teams/roster', {'season': 2027, 'team': 'Duke'})
    sample('roster Duke 2016', '/teams/roster', {'season': 2016, 'team': 'Duke'})
    sample('recruits 2026 class', '/recruiting/players', {'year': 2026})
    sample('recruits 2015 class', '/recruiting/players', {'year': 2015})
    sample('player season stats Duke 2026', '/stats/player/season', {'season': 2026, 'team': 'Duke'})
    sample('team season shooting Duke 2026', '/stats/team/shooting/season', {'season': 2026, 'team': 'Duke'})
    sample('adjusted ratings 2026', '/ratings/adjusted', {'season': 2026})
    sample('adjusted ratings 2015', '/ratings/adjusted', {'season': 2015})
    sample('SRS 2026', '/ratings/srs', {'season': 2026})
    sample('rankings 2026', '/rankings', {'season': 2026})
    sample('venues', '/venues', {})
    sample('media 2026 (1 day)', '/games/media', {'season': 2026, **day})
    if g26:
        sample('plays one game 2026', f'/plays/game/{g26}', {})
        sample('substitutions one game 2026', f'/substitutions/game/{g26}', {})
        sample('lineups one game 2026', f'/lineups/game/{g26}', {})
    if g15:
        sample('plays one game 2015', f'/plays/game/{g15}', {})
    sample('plays by date 2026 (1 day)', '/plays/date', {'date': '2026-01-10'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push', action='store_true')
    ap.add_argument('--seasons', default=','.join(str(s) for s in range(2014, 2028)))
    a = ap.parse_args()
    today = datetime.now(timezone.utc).date()
    say(f'CBBD probe v2 {OUT["run_utc"]}')
    say('=== Part 1: lines audit (D1-vs-D1 finals) ===')
    for s in [int(x) for x in a.seasons.split(',')]:
        audit_season(s, today)
        say(f'    [calls so far {B.STATE["calls"]}, cache hits {B.STATE["cached"]}]')
    endpoints()
    say(f'\nAPI calls this run: {B.STATE["calls"]} (cache hits {B.STATE["cached"]}) | quota remaining {B.STATE["quota"]}')
    OUT['calls'] = B.STATE['calls']
    OUT['quota_remaining'] = B.STATE['quota']
    REPORT.write_text('\n'.join(LOG) + '\n')
    JSON_OUT.write_text(json.dumps(OUT, indent=1, default=str))
    print(f'Saved {REPORT} and {JSON_OUT}')
    if a.push:
        subprocess.run(['git', 'add', str(REPORT), str(JSON_OUT)], cwd=ROOT, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'CBB probe v2 report'], cwd=ROOT, check=False)
        subprocess.run(['git', 'pull', '--rebase', '--autostash', '-q'], cwd=ROOT, check=False)
        subprocess.run(['git', 'push', '-q'], cwd=ROOT, check=True)
        print('Pushed probe v2 report')


if __name__ == '__main__':
    main()
