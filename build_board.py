"""SAIF board builder: score a week with Alpha + Beta and write site/index.html.

Replaces the week-hardcoded scripts (build_week6_board / build_week6_html /
add+inject_injuries). Run after saif_pull_all.py.

    python build_board.py --week 7
    python build_board.py --week 7 --season 2026 --out site

Project layout it expects (relative to this file):
    cfb_fullseason_data_<season>/        <- written by saif_pull_all.py
        expanded_features.csv
        raw/*.json                       (CFBD cache; /games used for opponent ratings)
        sportsdataio/raw/injured_players.json, teams.json   (optional)
    models/fitted_model.json             Alpha (frozen)
    models/beta_model.json               Beta (reconstruction)
    models/cfbd_conferences_2022-2025.csv
    models/summary.json                  backtest buckets table
    assets/logo_tag.txt                  <img ...> tag with the SAIF logo
Writes: docs/index.html (the published page) and state/week<N>_scored.pkl (opening lines, so line moves persist)
"""
import argparse
import glob
import html as htmlmod
import json
import pickle
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

HERE = Path(__file__).resolve().parent
RATING_ALPHA = 8.0
e = htmlmod.escape
fmt = lambda x: ('+' if x > 0 else '−' if x < 0 else '') + f'{abs(x):.2f}'

FEATURE_LABELS = {
    'diff_ppa': 'Net PPA (efficiency)', 'diff_successRate': 'Success rate',
    'diff_explosiveness': 'Explosiveness', 'diff_pointsPerOpportunity': 'Points per opportunity',
    'diff_havoc_total': 'Havoc rate', 'diff_turnover_margin': 'Turnover margin',
    'neutral_site': 'Neutral site', 'rest_difference': 'Rest advantage',
    'oa_offense_difference': 'Opp-adjusted offense', 'oa_defense_difference': 'Opp-adjusted defense',
    'tier_gap': 'Conference tier gap',
}


# ------------------------------------------------------------------ scoring
def load_games(data_dir, season):
    for f in glob.glob(str(data_dir / 'raw' / '*.json')):
        d = json.load(open(f))
        if d['request']['endpoint'] == '/games' and d['request']['params'].get('year') == season:
            return d['data']
    raise SystemExit(f'No cached /games response for {season} in {data_dir}/raw -- run saif_pull_all.py first.')


def eligible_games(schedule, week):
    out = []
    for g in schedule:
        if g.get('completed') is not True or g.get('week', 999) >= week:
            continue
        if g.get('homeClassification') != 'fbs' or g.get('awayClassification') != 'fbs':
            continue
        if g.get('homePoints') is None or g.get('awayPoints') is None:
            continue
        out.append(g)
    return out


def fit_ratings(games):
    teams = sorted({g[s + 'Team'] for g in games for s in ('home', 'away')})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X = np.zeros((len(games) * 2, n * 2 + 1))
    y = np.zeros(len(games) * 2)
    for k, g in enumerate(games):
        h, a = idx[g['homeTeam']], idx[g['awayTeam']]
        loc = 0 if g.get('neutralSite') else .5
        X[2 * k, h] = 1; X[2 * k, n + a] = -1; X[2 * k, -1] = loc; y[2 * k] = g['homePoints']
        X[2 * k + 1, a] = 1; X[2 * k + 1, n + h] = -1; X[2 * k + 1, -1] = -loc; y[2 * k + 1] = g['awayPoints']
    m = Ridge(alpha=RATING_ALPHA, solver='cholesky').fit(X, y)
    return {t: {'offense': float(m.coef_[i]), 'defense': float(m.coef_[n + i])} for t, i in idx.items()}


def score_with_contribs(row, m):
    """Exact linear decomposition; missingness-indicator terms fold into their parent field."""
    x, missing = [], []
    for i, key in enumerate(m['spec']['fields']):
        v = row[key]
        absent = pd.isna(v)
        missing.append(absent)
        x.append(m['imputer_statistics'][i] if absent else float(v))
    x.extend(float(missing[i]) for i in m['imputer_indicator_features'])
    contribs = [(v - mu) / sc * c for v, mu, sc, c in zip(x, m['scaler_mean'], m['scaler_scale'], m['coefficients'])]
    margin = m['intercept'] + sum(contribs)
    n_named = len(m['spec']['fields'])
    named = contribs[:n_named]
    for j, fi in enumerate(m['imputer_indicator_features']):
        named[fi] += contribs[n_named + j]
    return margin, dict(zip(m['spec']['fields'], named))


def score_week(data_dir, season, week):
    ratings = fit_ratings(eligible_games(load_games(data_dir, season), week))
    feat = pd.read_csv(data_dir / 'expanded_features.csv', low_memory=False)
    wk = feat[(feat.season == season) & (feat.week == week)].copy()
    if wk.empty:
        raise SystemExit(f'No rows for season {season} week {week} in expanded_features.csv')
    zero = {'offense': 0., 'defense': 0.}
    wk['oa_offense_difference'] = wk.apply(lambda r: ratings.get(r.home_team, zero)['offense'] - ratings.get(r.away_team, zero)['offense'], axis=1)
    wk['oa_defense_difference'] = wk.apply(lambda r: ratings.get(r.home_team, zero)['defense'] - ratings.get(r.away_team, zero)['defense'], axis=1)

    conf = pd.read_csv(HERE / 'models' / 'cfbd_conferences_2022-2025.csv')
    c25 = conf[conf.season == 2025].set_index('team')['conference'].to_dict()
    P4 = {'ACC', 'Big Ten', 'Big 12', 'SEC'}
    G5 = {'American Athletic', 'Conference USA', 'Mid-American', 'Mountain West', 'Sun Belt'}
    tier = lambda c: 'P4' if c in P4 else 'G5' if c in G5 else 'other'

    def tier_gap(r):
        ht, at = tier(c25.get(r.home_team)), tier(c25.get(r.away_team))
        return 1 if (ht == 'P4' and at == 'G5') else -1 if (ht == 'G5' and at == 'P4') else 0
    wk['tier_gap'] = wk.apply(tier_gap, axis=1)

    alpha = json.load(open(HERE / 'models' / 'fitted_model.json'))
    beta = json.load(open(HERE / 'models' / 'beta_model.json'))
    for name, m, col in (('alpha', alpha, 'independent'), ('beta', beta, 'beta')):
        out = wk.apply(lambda r, m=m: score_with_contribs(r, m), axis=1)
        wk[f'{col}_margin'] = out.apply(lambda t: t[0])
        wk[f'{name}_contribs'] = out.apply(lambda t: t[1])
    wk['independent_fair_spread'] = -wk['independent_margin']
    wk['independent_edge'] = wk['independent_margin'] + wk['market_spread']
    wk['beta_fair_spread'] = -wk['beta_margin']
    wk['beta_edge'] = wk['beta_margin'] + wk['market_spread']
    wk = wk[wk.market_spread.notna()].copy()
    wk['kickoff_utc'] = pd.to_datetime(wk['kickoff_utc'], utc=True)
    return wk.sort_values('kickoff_utc').reset_index(drop=True)


# ------------------------------------------------------------------ injuries
NORM = lambda s: re.sub('[^a-z0-9]', '', s.lower())
ALIASES = {'App State': 'Appalachian State', 'Louisiana': 'Louisiana-Lafayette', 'NC State': 'North Carolina State',
           'UL Monroe': 'Louisiana-Monroe', "Hawai'i": 'Hawaii', 'San José State': 'San Jose State',
           'UConn': 'Connecticut'}
PRIORITY = {'Out': 0, 'Doubtful': 1, 'Questionable': 2, 'Probable': 3}


def load_injuries(data_dir, team_names):
    base = data_dir / 'sportsdataio' / 'raw'
    if not (base / 'injured_players.json').exists():
        return None
    teams = json.load(open(base / 'teams.json'))['data']
    wrapper = json.load(open(base / 'injured_players.json'))
    cross, unmatched = {}, []
    for name in team_names:
        tn = NORM(ALIASES.get(name, name))
        hit = [t for t in teams if tn in [NORM(t.get(k) or '') for k in ('School', 'ShortDisplayName', 'Key', 'Name')]]
        if len(hit) == 1:
            cross[name] = hit[0]['TeamID']
        else:
            unmatched.append(name)
    if unmatched:
        print('Injury crosswalk unmatched (add to ALIASES):', unmatched)
    stamp = datetime.fromisoformat(wrapper['retrieved_at_utc'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York'))
    return {'players': wrapper['data'], 'cross': cross, 'label': stamp.strftime('%b %d, %Y · ') + str(int(stamp.strftime('%I'))) + stamp.strftime(':%M %p ET')}


def injury_block(inj, team):
    tid = inj['cross'].get(team)
    people = sorted([p for p in inj['players'] if p['TeamID'] == tid],
                    key=lambda p: (p['Position'] != 'QB', PRIORITY.get(p['InjuryStatus'], 9), p['LastName'], p['FirstName'])) if tid else []
    s = f'<section class="injury-team"><h3>{e(team)} · {len(people)} listed</h3>'
    if not people:
        s += '<p class="note">No availability reports listed in this snapshot. This does not confirm a healthy roster.</p>'
    for p in people:
        s += (f'<div class="injury-player"><div><b>{e(p["FirstName"])} {e(p["LastName"])}</b> · {e(p["Position"])} '
              f'<span class="injury-status">{e(p["InjuryStatus"])}</span></div>')
        if p.get('InjuryBodyPart'):
            s += f'<p>{e(p["InjuryBodyPart"])}</p>'
        if p.get('InjuryNotes'):
            s += f'<p class="injury-time">{e(p["InjuryNotes"])}</p>'
        s += '</div>'
    return s + '</section>', len(people)


# ------------------------------------------------------------------ html
def edge_class(x):
    return 'edge-strong' if abs(x) >= 3 else 'edge-mid' if abs(x) >= 1.5 else 'edge-weak'


def contrib_rows(contribs, home, away, max_rows=8):
    items = sorted([kv for kv in contribs.items() if kv[0] in FEATURE_LABELS], key=lambda kv: -abs(kv[1]))[:max_rows]
    if not items:
        return ''
    peak = max(abs(v) for _, v in items) or 1e-9
    rows = []
    for key, val in items:
        pct = min(abs(val) / peak * 50, 50)
        team, cls = (home, 'home') if val > 0 else (away, 'away')
        fill = (f'<div class="contrib-fill home" style="left:50%;width:{pct:.1f}%"></div>' if val > 0
                else f'<div class="contrib-fill away" style="right:50%;width:{pct:.1f}%"></div>')
        rows.append(f'<div class="contrib-row"><span class="contrib-label">{e(FEATURE_LABELS[key])}</span>'
                    f'<div class="contrib-track"><div class="contrib-mid"></div>{fill}</div>'
                    f'<span class="contrib-val {cls}">{fmt(val)} &rarr; {e(team)}</span></div>')
    return ''.join(rows)


# Everything a reader sees is written as a bet: team + signed number, favorite with a minus.
# market_spread / *_fair_spread are HOME-relative sportsbook spreads (negative = home favored);
# *_edge = model margin + market spread (positive = take the home side at the market number).
MIN_EDGE = 1.5  # below this a model's side shows as "No play"


def sgn(x):
    return 'PK' if abs(x) < .05 else ('+' if x > 0 else '−') + f'{abs(x):.1f}'


def bet_line(spread, home, away):
    """Home-relative spread -> 'Favorite −3.0' (or Pick'em)."""
    if pd.isna(spread):
        return '—'
    if abs(spread) < .05:
        return "Pick'em"
    return f'{e(home)}&nbsp;{sgn(spread)}' if spread < 0 else f'{e(away)}&nbsp;{sgn(-spread)}'


def model_tile(name, edge, fair_spread, r):
    team = r.home_team if edge > 0 else r.away_team
    num = r.market_spread if edge > 0 else -r.market_spread
    pick = (f'<span class="pick {edge_class(edge)}">{e(team)}&nbsp;{sgn(num)}</span>' if abs(edge) >= MIN_EDGE
            else '<span class="noplay">No play</span>')
    return (f'<div class="mtile"><div class="mlabel">{name}</div>{pick}'
            f'<div class="msub">Model <b>{bet_line(fair_spread, r.home_team, r.away_team)}</b> '
            f'<span class="edge nw"><span class="dot">&middot; </span>Edge {abs(edge):.1f}</span></div></div>')


def build_card(r, inj):
    t = pd.Timestamp(r.kickoff_utc).tz_convert('America/New_York')
    day = t.strftime('%A')
    ae, be = r.independent_edge, r.beta_edge
    tg = '' if r.tier_gap == 0 else ('<span class="tiertag">P4 vs G5</span>' if r.tier_gap == 1 else '<span class="tiertag">G5 vs P4</span>')
    neutral = bool(getattr(r, 'neutral_site', False))
    inj_html = ''
    if inj:
        hb, hn = injury_block(inj, r.home_team)
        ab, an = injury_block(inj, r.away_team)
        inj_html = f'<details class="injuries"><summary>Injuries &amp; availability ({hn + an} listed)</summary>{hb}{ab}</details>'
    final = ''
    if pd.notna(getattr(r, 'actual_margin', np.nan)):
        final = f'<span class="finaltag">Final: {e(r.home_team if r.actual_margin > 0 else r.away_team)} by {abs(r.actual_margin):.0f}</span>'
    prev = getattr(r, 'prev_spread', np.nan)
    moved = (f' <span class="movetag">(was {bet_line(prev, r.home_team, r.away_team)})</span>'
             if pd.notna(prev) and abs(prev - r.market_spread) >= .25 else '')
    when = f"{t.strftime('%a, %b')} {t.day} &middot; {t.strftime('%I:%M %p').lstrip('0')} ET"
    return f'''<article class="game" data-search="{e((r.home_team + ' ' + r.away_team).lower())}" data-day="{day}" data-side="{'home' if ae > 0 else 'away'}" data-edge="{max(abs(ae), abs(be))}" data-time="{t.timestamp()}">
 <div class="meta"><span>{when}</span>{' <span>Neutral site</span>' if neutral else ''}{tg}{final}</div>
 <h2>{e(r.away_team)} <small>{'vs.' if neutral else 'at'}</small> {e(r.home_team)}</h2>
 <p class="line"><span class="lbl">Line</span> <b>{bet_line(r.market_spread, r.home_team, r.away_team)}</b>{moved}</p>
 <div class="models">{model_tile('Alpha', ae, r.independent_fair_spread, r)}{model_tile('Beta', be, r.beta_fair_spread, r)}</div>
<details class="contrib"><summary>Where the margin comes from</summary>
 <p class="contrib-sub">Alpha</p>{contrib_rows(r.alpha_contribs, r.home_team, r.away_team)}
 <p class="contrib-sub">Beta</p>{contrib_rows(r.beta_contribs, r.home_team, r.away_team)}
 <p class="contrib-note">Exact linear decomposition of each model's own prediction &mdash; intercept + each feature's standardized value &times; its fitted coefficient. Bars run from the center: right/gold favors {e(r.home_team)} (home), left/blue favors {e(r.away_team)} (away).</p>
</details>{inj_html}
</article>'''


def build_page(wk, week, season, inj):
    template = (HERE / 'assets' / 'page_template.html').read_text(encoding='utf-8')
    logo = (HERE / 'assets' / 'logo_tag.txt').read_text(encoding='utf-8').strip()
    summary = json.load(open(HERE / 'models' / 'summary.json'))
    rows_html = ''.join(f'<tr><td>{e(b["sample"])}</td><td>{e(b["difference_bucket"])}</td><td>{b["wins"]}&ndash;{b["losses"]}&ndash;{b["pushes"]}</td><td>{b["win_rate"]:.1%}</td></tr>' for b in summary['buckets'])
    buckets = ('<table><thead><tr><th>Sample</th><th>Difference &middot; pts</th><th>W&ndash;L&ndash;P</th>'
               '<th>ATS &middot; excludes pushes (Alpha)</th></tr></thead><tbody>' + rows_html + '</tbody></table>')
    et = wk.kickoff_utc.dt.tz_convert('America/New_York')
    span = f"{et.min().strftime('%B')} {et.min().day}&ndash;{et.max().day}, {season}" if et.min().month == et.max().month \
        else f"{et.min().strftime('%B')} {et.min().day} &ndash; {et.max().strftime('%B')} {et.max().day}, {season}"
    n_tier = int((wk.tier_gap != 0).sum())
    if inj:
        inj_note = (f'<p class="note"><b>Availability snapshot: {inj["label"]}.</b> Open "Injuries &amp; availability" on each game for player reports. '
                    'This is a saved snapshot, not live data; no injury adjustments have been applied to either model.</p>')
    else:
        inj_note = '<p class="note"><b>No injury snapshot this week.</b> Check each team\'s current injury report manually before betting.</p>'
    cards = ''.join(build_card(r, inj) for r in wk.itertuples())
    repl = {'{{LOGO}}': logo, '{{WEEK}}': str(week), '{{SPAN}}': span, '{{N_GAMES}}': str(len(wk)),
            '{{N_TIER}}': str(n_tier), '{{INJ_NOTE}}': inj_note, '{{BUCKETS}}': buckets,
            '{{THROUGH_WEEK}}': str(week - 1), '{{CARDS}}': cards}
    for k, v in repl.items():
        template = template.replace(k, v)
    return template


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--week', type=int, required=True)
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--out', default='docs')
    a = ap.parse_args()
    data_dir = HERE / f'cfb_fullseason_data_{a.season}'
    wk = score_week(data_dir, a.season, a.week)
    names = sorted(set(wk.home_team) | set(wk.away_team))
    inj = load_injuries(data_dir, names)
    out = HERE / a.out
    out.mkdir(parents=True, exist_ok=True)
    state = HERE / 'state'
    state.mkdir(exist_ok=True)
    prev_pkl = state / f'week{a.week}_scored.pkl'
    if prev_pkl.exists():  # earlier build of this week: remember its lines so moves show on the cards
        prev = pd.read_pickle(prev_pkl)
        # keep the FIRST line this tool saw for the game, so repeated rebuilds don't erase the move
        prev['prev_spread'] = prev['prev_spread'].fillna(prev['market_spread']) if 'prev_spread' in prev else prev['market_spread']
        prev = prev[['home_team', 'away_team', 'prev_spread']]
        wk = wk.merge(prev, on=['home_team', 'away_team'], how='left')
    wk.to_pickle(prev_pkl)
    (out / 'index.html').write_text(build_page(wk, a.week, a.season, inj), encoding='utf-8')
    print(f'Week {a.week}: {len(wk)} games scored -> {out / "index.html"} (injuries: {"yes" if inj else "none"})')


if __name__ == '__main__':
    main()
