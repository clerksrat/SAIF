"""Gamma: the Phase 2 STATS model (ridge on pregame CFBD features), frozen and run as a SHADOW.

    python cfb_phase2/gamma.py export --hist <pack training_data.csv>   # once: freeze the model (done 2026-11-08)
    python cfb_phase2/gamma.py build --week 11                         # Pi: API -> pack-format features -> scores
    python cfb_phase2/gamma.py validate --built state/gamma/week11_features.csv --patreon <training_data_2026_week11.csv>
    python cfb_phase2/gamma.py openers --years 2016-2025               # Pi: historical opening lines (1 call/season)

build writes state/gamma/week<N>_features.csv (pack column names) and state/gamma/week<N>_scored.csv
(game_id, gamma_margin = predicted home margin, built_utc). build_board.py merges gamma_margin onto the
board, saif_policy records it at entry lock, grade_week.py grades it. Gamma is never a play.

Feature sources (CFBD's own recipe for the training pack, blog "From Model Training Pack to Predictions"):
  /games (schedule), /ratings/elo (week = the board week), /talent, /wepa/team/season (opponent-adjusted,
  season to date at call time), /stats/season/advanced endWeek = week-1 (havoc, points per opportunity,
  field position). /wepa has no week filter we rely on: a Sunday/Monday call is "through last week" only
  if CFBD has already updated -- `validate` against the Patreon file is how we check that.
About 5 API calls per build. /wepa may need a Patreon feature flag ('adjustedMetrics').
"""
import argparse, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from backtest_pack import features, Ridge  # noqa: E402

FROZEN = HERE / 'gamma_frozen_v1.json'
OUT = REPO / 'state' / 'gamma'
BASE = 'https://api.collegefootballdata.com'

# pack column suffix -> candidate flattened /wepa keys (lowercase, dots removed); first hit wins
WEPA_MAP = {
    'adjusted_epa': ['epatotal', 'epa'], 'adjusted_epa_allowed': ['epaallowedtotal', 'epaallowed'],
    'adjusted_rushing_epa': ['eparushing'], 'adjusted_rushing_epa_allowed': ['epaallowedrushing'],
    'adjusted_passing_epa': ['epapassing'], 'adjusted_passing_epa_allowed': ['epaallowedpassing'],
    'adjusted_success': ['successratetotal', 'successrate'], 'adjusted_success_allowed': ['successrateallowedtotal', 'successrateallowed'],
    'adjusted_standard_down_success': ['successratestandarddowns'], 'adjusted_standard_down_success_allowed': ['successrateallowedstandarddowns'],
    'adjusted_passing_down_success': ['successratepassingdowns'], 'adjusted_passing_down_success_allowed': ['successrateallowedpassingdowns'],
    'adjusted_line_yards': ['rushinglineyards', 'lineyards'], 'adjusted_line_yards_allowed': ['rushingallowedlineyards', 'lineyardsallowed'],
    'adjusted_second_level_yards': ['rushingsecondlevelyards', 'secondlevelyards'],
    'adjusted_second_level_yards_allowed': ['rushingallowedsecondlevelyards', 'secondlevelyardsallowed'],
    'adjusted_open_field_yards': ['rushingopenfieldyards', 'openfieldyards'],
    'adjusted_open_field_yards_allowed': ['rushingallowedopenfieldyards', 'openfieldyardsallowed'],
    'adjusted_explosiveness': ['explosivenesstotal', 'explosiveness'], 'adjusted_explosiveness_allowed': ['explosivenessallowedtotal', 'explosivenessallowed'],
    'adjusted_rush_explosiveness': ['explosivenessrushing'], 'adjusted_rush_explosiveness_allowed': ['explosivenessallowedrushing'],
    'adjusted_pass_explosiveness': ['explosivenesspassing'], 'adjusted_pass_explosiveness_allowed': ['explosivenessallowedpassing'],
}
ADV_MAP = {  # pack suffix -> flattened /stats/season/advanced key
    'total_havoc_offense': 'offensehavoctotal', 'front_seven_havoc_offense': 'offensehavocfrontseven', 'db_havoc_offense': 'offensehavocdb',
    'total_havoc_defense': 'defensehavoctotal', 'front_seven_havoc_defense': 'defensehavocfrontseven', 'db_havoc_defense': 'defensehavocdb',
    'points_per_opportunity_offense': 'offensepointsperopportunity', 'points_per_opportunity_defense': 'defensepointsperopportunity',
    'avg_start_offense': 'offensefieldpositionaveragestart', 'avg_start_defense': 'defensefieldpositionaveragestart',
}


def flat(d, prefix=''):
    out = {}
    for k, v in (d or {}).items():
        key = prefix + re.sub(r'[^a-z0-9]', '', str(k).lower())
        if isinstance(v, dict):
            out.update(flat(v, key))
        else:
            out[key] = v
    return out


# ------------------------------------------------------------------ export (run once, off-Pi)
def export(hist):
    raw = pd.read_csv(hist)
    d = raw[(raw.season_type == 'regular') & raw.spread.notna()].copy().reset_index(drop=True)
    X = features(d)
    params = json.load(open(HERE / 'params.json'))
    m = Ridge(params['lam_stats']).fit(X, -d['margin'])
    FROZEN.write_text(json.dumps({
        'name': 'gamma_frozen_v1', 'frozen_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'trained_on': 'CFBD Model Training Pack 2026 + 2026-10-06 update, regular season 2016-19/2021-25 Week 5+, n=%d' % len(d),
        'target': 'home margin (home - away)', 'lambda': params['lam_stats'],
        'features': list(X.columns), 'median': X.median().round(8).tolist(), 'mean': m.mu.round(8).tolist(),
        'sd': m.sd.round(8).tolist(), 'coef': [round(float(b), 8) for b in m.b], 'intercept': float(m.b0)}, indent=1))
    print(f'Frozen {FROZEN.name}: {len(d)} games, lambda {params["lam_stats"]}')


def load_frozen():
    f = json.load(open(FROZEN))
    m = Ridge(f['lambda'])
    m.med = pd.Series(f['median'], index=f['features'])
    m.mu = pd.Series(f['mean'], index=f['features'])
    m.sd = pd.Series(f['sd'], index=f['features'])
    m.b = np.array(f['coef'])
    m.b0 = f['intercept']
    return m, f['features']


def score(df):
    m, cols = load_frozen()
    X = features(df)
    return m.predict(X[cols])


# ------------------------------------------------------------------ API (Pi)
def api(path, params):
    key = os.environ.get('CFBD_API_KEY', '').strip()
    if not key:
        raise SystemExit('CFBD_API_KEY not set')
    req = Request(BASE + path + '?' + urlencode(params), headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    for attempt in range(5):
        try:
            with urlopen(req, timeout=60) as r:
                return json.load(r)
        except HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit(f'CFBD HTTP {e.code} on {path} (key or tier does not allow it)') from None
            if e.code != 429 and e.code < 500:
                raise SystemExit(f'CFBD HTTP {e.code} on {path}') from None
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2 ** attempt)
    raise SystemExit(f'CFBD unreachable: {path}')


def build(season, week):
    games = api('/games', {'year': season, 'week': week, 'seasonType': 'regular', 'classification': 'fbs'})
    elo = {r['team']: r.get('elo') for r in api('/ratings/elo', {'year': season, 'week': week})}
    talent = {r['team']: r.get('talent') for r in api('/talent', {'year': season})}
    wepa_raw = api('/wepa/team/season', {'year': season})
    adv_raw = api('/stats/season/advanced', {'year': season, 'endWeek': week - 1, 'excludeGarbageTime': 'false'})
    wepa = {r.get('team'): flat(r) for r in wepa_raw}
    adv = {r.get('team'): flat(r) for r in adv_raw}
    if wepa_raw:
        print('[gamma] /wepa keys:', sorted(flat(wepa_raw[0]))[:60])
    missing_keys = set()

    def team_cols(team, side):
        row = {}
        w, a = wepa.get(team, {}), adv.get(team, {})
        for col, cands in WEPA_MAP.items():
            hit = next((c for c in cands if c in w), None)
            if hit is None:
                missing_keys.add(col)
            row[f'{side}_{col}'] = w.get(hit) if hit else np.nan
        for col, k in ADV_MAP.items():
            row[f'{side}_{col}'] = a.get(k, np.nan)
        row[f'{side}_elo'] = elo.get(team, np.nan)
        row[f'{side}_talent'] = talent.get(team, 0.0)
        return row

    rows = []
    for g in games:
        h, aw = g.get('homeTeam'), g.get('awayTeam')
        r = {'id': g.get('id'), 'start_date': g.get('startDate'), 'season': season, 'season_type': 'regular', 'week': week,
             'neutral_site': bool(g.get('neutralSite')), 'home_team': h, 'home_conference': g.get('homeConference'),
             'away_team': aw, 'away_conference': g.get('awayConference')}
        r.update(team_cols(h, 'home'))
        r.update(team_cols(aw, 'away'))
        rows.append(r)
    df = pd.DataFrame(rows)
    if missing_keys:
        print('[gamma] WARNING: no /wepa field found for', sorted(missing_keys))
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    df['built_utc'] = now
    df.to_csv(OUT / f'week{week}_features.csv', index=False)
    ok = df[[c for c in df.columns if c.startswith(('home_adjusted_epa', 'away_adjusted_epa', 'home_elo', 'away_elo'))]].notna().all(axis=1)
    sc = pd.DataFrame({'game_id': df['id'], 'home_team': df.home_team, 'away_team': df.away_team,
                       'gamma_margin': np.where(ok, score(df), np.nan), 'built_utc': now})
    sc.to_csv(OUT / f'week{week}_scored.csv', index=False)
    print(f'[gamma] week {week}: {len(df)} games, {int(ok.sum())} scored -> {OUT / f"week{week}_scored.csv"}')


def validate(built, patreon):
    b, p = pd.read_csv(built), pd.read_csv(patreon)
    j = b.merge(p, on='id', suffixes=('_api', '_pat'))
    print(f'{len(j)} of {len(p)} Patreon games matched')
    rows = []
    for c in p.columns:
        if c + '_api' not in j or not pd.api.types.is_numeric_dtype(p[c]) or pd.api.types.is_bool_dtype(p[c]):
            continue
        x = pd.to_numeric(j[c + '_api'], errors='coerce').astype(float)
        y = pd.to_numeric(j[c + '_pat'], errors='coerce').astype(float)
        ok = x.notna() & y.notna()
        if ok.sum() < 5:
            rows.append({'field': c, 'n': int(ok.sum())})
            continue
        sd_ok = x[ok].std() > 0 and y[ok].std() > 0
        rows.append({'field': c, 'n': int(ok.sum()), 'corr': round(float(np.corrcoef(x[ok], y[ok])[0, 1]), 4) if sd_ok else None,
                     'mean_abs_diff': float((x[ok] - y[ok]).abs().mean()), 'pat_sd': float(y[ok].std())})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    gp, ga = score(j.rename(columns=lambda c: c[:-4] if c.endswith('_pat') else c)), \
        score(j.rename(columns=lambda c: c[:-4] if c.endswith('_api') else c))
    print(f'Gamma margin from API vs Patreon features: corr {np.corrcoef(ga, gp)[0, 1]:.4f}, '
          f'mean |diff| {np.abs(ga - gp).mean():.2f} pts')


def openers(years):
    lo, hi = (int(x) for x in years.split('-'))
    out = []
    for y in range(lo, hi + 1):
        if y == 2020:
            continue
        for g in api('/lines', {'year': y, 'seasonType': 'regular'}):
            for ln in g.get('lines') or []:
                out.append({'id': g.get('id'), 'season': y, 'week': g.get('week'), 'home_team': g.get('homeTeam'),
                            'away_team': g.get('awayTeam'), 'provider': ln.get('provider'), 'spread': ln.get('spread'),
                            'spread_open': ln.get('spreadOpen')})
        print(f'[openers] {y}: {sum(1 for r in out if r["season"] == y)} provider rows')
    f = HERE / 'data' / 'cfbd_lines_openers.csv.gz'
    f.parent.mkdir(exist_ok=True)
    pd.DataFrame(out).to_csv(f, index=False)
    print(f'[openers] wrote {f}')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export'); e.add_argument('--hist', required=True)
    b = sub.add_parser('build'); b.add_argument('--week', type=int, required=True); b.add_argument('--season', type=int, default=2026)
    v = sub.add_parser('validate'); v.add_argument('--built', required=True); v.add_argument('--patreon', required=True)
    o = sub.add_parser('openers'); o.add_argument('--years', default='2016-2025')
    a = ap.parse_args()
    if a.cmd in ('build', 'openers'):
        try:
            sys.path.insert(0, str(REPO))
            import saif_pull_all  # noqa: F401  (loads .env)
        except Exception:
            pass
    {'export': lambda: export(a.hist), 'build': lambda: build(a.season, a.week),
     'validate': lambda: validate(a.built, a.patreon), 'openers': lambda: openers(a.years)}[a.cmd]()


if __name__ == '__main__':
    main()
