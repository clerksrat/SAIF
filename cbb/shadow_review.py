"""Week-1 review of the frozen v1 CBB shadow test (freeze commit cdacf27). Pre-specified rules only.

    python3 cbb/shadow_review.py        # -> cbb/shadow_review_week1.md

Rules fixed before the week (no changes after seeing results): models A0 / A1 / C1 from
models/frozen_v1.json as logged; side candidate = |model - line| >= 3 points, total candidate >= 4,
both measured against each book's own MORNING line. Lines are in "points" form: v = -home spread for
sides, v = total for totals; side = sign(model - v_morning).

Executable prices = the logged morning quotes at FanDuel, DraftKings, BetRivers (point + American odds,
feed timestamp). Pre-tip = our own timestamped snapshot (last before tip). The CBBD opener is an untimed
reference only and never priced. ONE WEEK: this tests logging and market movement, not profitability.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from odds_match import Matcher
from ratings import read

HERE = Path(__file__).resolve().parent
BOOKS = ['fd', 'dk', 'br']
NAMES = {'fd': 'FanDuel', 'dk': 'DraftKings', 'br': 'BetRivers'}
THR = {'side': 3.0, 'total': 4.0}
RNG = np.random.default_rng(11)
OUT = []


def say(s=''):
    print(s, flush=True)
    OUT.append(s)


# ------------------------------------------------------------------ assemble
def pretip(teams):
    c = pd.read_csv(HERE / 'state' / 'closing_lines.csv')
    c['tip'] = pd.to_datetime(c.commence_time, utc=True, format='ISO8601')
    c['snap'] = pd.to_datetime(c.snapshot_utc, utc=True, format='ISO8601')
    c = c[c.snap < c.tip].sort_values('snap')
    m = Matcher(teams)
    c['h'], c['a'] = c.home_team.map(m.team), c.away_team.map(m.team)
    return c.dropna(subset=['h', 'a'])


def attach_pretip(s, c):
    cols = {b: (f'{b}_spread_home', f'{b}_total') for b in BOOKS}
    out = []
    for r in s.itertuples():
        x = c[(((c.h == r.home) & (c.a == r.away)) | ((c.h == r.away) & (c.a == r.home)))
              & ((c.tip - r.tip).abs() <= pd.Timedelta(hours=6))]
        row = {'pt_snap': pd.NaT, 'pt_min_before': np.nan, 'pt_reversed': np.nan}
        if len(x):
            last = x.iloc[-1]
            rev = last.h != r.home
            row.update(pt_snap=last.snap, pt_min_before=(r.tip - last.snap).total_seconds() / 60, pt_reversed=rev,
                       pt_cons_spread=(-last.close_spread_home if rev else last.close_spread_home),
                       pt_cons_total=last.close_total)
            for b, (sc, tc) in cols.items():
                v = last[sc]
                row[f'pt_{b}_spread'] = (-v if rev else v) if pd.notna(v) else np.nan
                row[f'pt_{b}_total'] = last[tc]
        out.append(row)
    return pd.concat([s.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def load_all():
    s = pd.read_csv(HERE / 'state' / 'shadow_entries.csv')
    s['tip'] = pd.to_datetime(s.tip_utc, utc=True, format='ISO8601')
    s['feed'] = pd.to_datetime(s.feed_utc, utc=True, format='ISO8601')
    g = read('games', {2027})
    teams = sorted(set(g.homeTeam) | set(g.awayTeam))
    s = attach_pretip(s, pretip(teams))
    fin = g[g.status == 'final'].set_index('id')
    s['final'] = s.game_id.isin(fin.index)
    s['margin'] = s.game_id.map(fin.homePoints - fin.awayPoints)
    s['tot_pts'] = s.game_id.map(fin.homePoints + fin.awayPoints)
    l = read('lines', {2027})
    cl = l.groupby('game_id').agg(cbbd_close_spread=('spread', 'median'), cbbd_close_total=('overUnder', 'median'))
    s = s.merge(cl, left_on='game_id', right_index=True, how='left')
    return s


# ------------------------------------------------------------------ helpers
def payout(odds):
    return np.where(odds > 0, odds / 100, 100 / np.abs(odds))


def cluster_ci(df, stat, key, n=1000):
    groups = df.groupby(key).indices
    keys = list(groups)
    if len(keys) < 3:
        return (np.nan, np.nan)
    vals = []
    for _ in range(n):
        pick = RNG.choice(keys, len(keys))
        idx = np.concatenate([groups[k] for k in pick])
        vals.append(stat(df.iloc[idx]))
    return tuple(np.nanpercentile(vals, [2.5, 97.5]))


def ci_txt(df, stat):
    d = cluster_ci(df, stat, 'date')
    t = cluster_ci(df, stat, 'home')
    return f'{stat(df):+.2f} (date-clustered {d[0]:+.2f} to {d[1]:+.2f}; team-clustered {t[0]:+.2f} to {t[1]:+.2f})'


def market_cols(kind, b):
    if kind == 'side':
        return f'{b}_spread_home', f'pt_{b}_spread', f'{b}_spread_home_price', f'{b}_spread_away_price'
    return f'{b}_total', f'pt_{b}_total', f'{b}_over_price', f'{b}_under_price'


def v(kind, x):                       # points form
    return -x if kind == 'side' else x


def model_col(kind, m):
    return f'{m}_margin' if kind == 'side' else f'{m}_total'


# ------------------------------------------------------------------ sections
def sec_quotes(s):
    say('## 1. Quote availability, timing and matching\n')
    say(f'Shadow games logged: {len(s)} ({s.date.min()} to {s.date.max()}); finals available for {int(s.final.sum())} '
        f'(CBBD data in the repo runs through {s[s.final].date.max()}).\n')
    say('| book | morning spread | morning total | morning before tip | pre-tip spread | pre-tip total | pre-tip before tip |')
    say('|---|---|---|---|---|---|---|')
    for b in BOOKS:
        ms, mt = s[f'{b}_spread_home'].notna(), s[f'{b}_total'].notna()
        ps, pt = s[f'pt_{b}_spread'].notna(), s[f'pt_{b}_total'].notna()
        say(f'| {NAMES[b]} | {ms.sum()} | {mt.sum()} | {(s.feed[ms] < s.tip[ms]).mean():.0%} | {ps.sum()} | {pt.sum()} '
            f'| {(s.pt_snap[ps] < s.tip[ps]).mean():.0%} |')
    h = (s.tip - s.feed).dt.total_seconds() / 3600
    say(f'\n- Morning quote taken {h.median():.1f} h before tip on median (range {h.min():.1f} to {h.max():.1f} h).')
    pm = s.pt_min_before.dropna()
    say(f'- Pre-tip snapshot exists for {len(pm)} of {len(s)} games; taken {pm.median():.0f} min before tip on median '
        f'(range {pm.min():.0f} to {pm.max():.0f}). Games without one: no snapshot in the window (rule: max one call per 45 min).')
    say(f'- Reversed listings (feed home/away opposite to ours) among pre-tip matches: {int(s.pt_reversed.fillna(False).sum())}; '
        'signs flipped to our home team.')
    # matching checks: same sign / magnitude as CBBD's own stored close
    chk = s[s.dk_spread_home.notna() & s.cbbd_close_spread.notna()]
    big = chk[(chk.cbbd_close_spread.abs() >= 3)]
    sign_bad = (np.sign(big.dk_spread_home) != np.sign(big.cbbd_close_spread)).sum()
    far = ((chk.dk_spread_home - chk.cbbd_close_spread).abs() > 6).sum()
    say(f'- Matching check vs CBBD stored close: DraftKings morning spread has the opposite sign on {sign_bad} of {len(big)} '
        f'games with |spread| >= 3; differs by more than 6 points on {far} of {len(chk)}.')
    odds = pd.concat([s[f'{b}_{c}'] for b in BOOKS for c in ('spread_home_price', 'spread_away_price', 'over_price', 'under_price')]).dropna()
    say(f'- Odds sanity: {len(odds)} prices logged, range {odds.min():.0f} to {odds.max():.0f}; '
        f'{((odds > -100) & (odds < 100)).sum()} invalid values between -100 and +100.\n')


def candidates(s, kind, m, b):
    """Rows where model vs this book's morning line passes the threshold."""
    lc, pc, hp, ap = market_cols(kind, b)
    x = s[s[lc].notna() & s[model_col(kind, m)].notna()].copy()
    x['vm'], x['vp'] = v(kind, x[lc]), v(kind, x[pc])
    x['edge'] = x[model_col(kind, m)] - x.vm
    x = x[x.edge.abs() >= THR[kind]].copy()
    x['side'] = np.sign(x.edge)
    x['move'] = x.side * (x.vp - x.vm)                  # > 0: line moved toward the model after we logged it
    x['odds'] = np.where(x.side > 0, x[hp], x[ap])        # side>0 = home / over
    x['book'] = b
    return x


def best_of_three(s, kind, m):
    """Per game: among books whose morning line passes the threshold for the model's side, take the best number
    (ties -> better odds). Side is decided by the median morning line of the three books."""
    rows = []
    for r in s.itertuples():
        lines = {b: getattr(r, market_cols(kind, b)[0]) for b in BOOKS}
        lines = {b: x for b, x in lines.items() if pd.notna(x)}
        mv = getattr(r, model_col(kind, m))
        if not lines or pd.isna(mv):
            continue
        side = np.sign(mv - v(kind, np.median(list(lines.values()))))
        best = None
        for b, ln in lines.items():
            vm = v(kind, ln)
            if side * (mv - vm) < THR[kind]:
                continue
            _, pc, hp, ap = market_cols(kind, b)
            o = getattr(r, hp if side > 0 else ap)
            key = (side * (-vm), o if pd.notna(o) else -999)          # lower vm for an over/home is better
            if best is None or key > best[0]:
                best = (key, b, vm, o, getattr(r, pc))
        if best:
            _, b, vm, o, pt = best
            rows.append({'game_id': r.game_id, 'date': r.date, 'home': r.home, 'book': b, 'side': side, 'vm': vm,
                         'vp': v(kind, pt) if pd.notna(pt) else np.nan, 'odds': o, 'final': r.final,
                         'y': r.margin if kind == 'side' else r.tot_pts, 'edge': mv - vm})
    x = pd.DataFrame(rows)
    if len(x):
        x['move'] = x.side * (x.vp - x.vm)
    return x


def sec_movement(s):
    say('## 2. Market movement, morning quote -> our pre-tip quote\n')
    say('Positive = the line moved toward the model after we logged it (our morning number was better than pre-tip).\n')
    for kind in ('side', 'total'):
        say(f'**{"Sides" if kind == "side" else "Totals"}** (candidates: edge >= {THR[kind]:g} vs the book\'s morning line)\n')
        say('| model | book | candidates | with pre-tip | toward / against / unchanged | mean move, pts (95% CIs) |')
        say('|---|---|---|---|---|---|')
        for m in ('A0', 'A1', 'C1'):
            for b in BOOKS + ['best3']:
                x = best_of_three(s, kind, m) if b == 'best3' else candidates(s, kind, m, b)
                y = x.dropna(subset=['move']) if len(x) else x
                if not len(y):
                    say(f'| {m} | {NAMES.get(b, "best of three")} | {len(x)} | 0 | | |')
                    continue
                say(f'| {m} | {NAMES.get(b, "best of three")} | {len(x)} | {len(y)} | {(y.move > 0).mean():.0%} / '
                    f'{(y.move < 0).mean():.0%} / {(y.move == 0).mean():.0%} | {ci_txt(y, lambda d: d.move.mean())} |')
        say('')
    say('**All games (not just candidates):** slope of (pre-tip − morning) on (model − morning), DraftKings lines\n')
    say('| market | model | games | slope | date-clustered 95% CI |')
    say('|---|---|---|---|---|')
    for kind in ('side', 'total'):
        lc, pc, _, _ = market_cols(kind, 'dk')
        for m in ('A0', 'A1', 'C1'):
            x = s[s[lc].notna() & s[pc].notna() & s[model_col(kind, m)].notna()].copy()
            if len(x) < 10:
                continue
            x['gap'] = x[model_col(kind, m)] - v(kind, x[lc])
            x['mv'] = v(kind, x[pc]) - v(kind, x[lc])
            slope = lambda d: (d.gap @ d.mv) / (d.gap @ d.gap)
            lo, hi = cluster_ci(x, slope, 'date')
            say(f'| {"sides" if kind == "side" else "totals"} | {m} | {len(x)} | {slope(x):+.3f} | {lo:+.3f} to {hi:+.3f} |')
    say('')


def sec_results(s):
    say('## 3. Results at the logged book prices — ONE WEEK, NOT A PROFITABILITY TEST\n')
    say('Graded at the actual morning number and American odds. Pushes return the stake.\n')
    say('| market | model | prices | bets graded | record | units (1u stakes) | ROI (date-clustered 95% CI) |')
    say('|---|---|---|---|---|---|---|')
    for kind in ('side', 'total'):
        for m in ('A0', 'A1', 'C1'):
            for lab, x in (('best of three', best_of_three(s, kind, m)), ('DraftKings only', candidates(s, kind, m, 'dk'))):
                if not len(x):
                    continue
                if 'y' not in x:
                    x['y'] = x.margin if kind == 'side' else x.tot_pts
                x = x[x.final & x.odds.notna()].copy()
                if not len(x):
                    continue
                cover = x.side * (x.y - x.vm)
                x['pnl'] = np.where(cover > 0, payout(x.odds.values), np.where(cover < 0, -1.0, 0.0))
                w, l, p = int((cover > 0).sum()), int((cover < 0).sum()), int((cover == 0).sum())
                roi = lambda d: d.pnl.sum() / len(d)
                lo, hi = cluster_ci(x, roi, 'date')
                say(f'| {"sides" if kind == "side" else "totals"} | {m} | {lab} | {len(x)} | {w}-{l}-{p} | {x.pnl.sum():+.1f}u '
                    f'| {roi(x):+.1%} ({lo:+.1%} to {hi:+.1%}) |')
    say('')


def sec_opener(s):
    say('## 4. CBBD opener — untimed reference only (never priced)\n')
    say('Movement from CBBD\'s stored opener to our timestamped pre-tip consensus, on the model\'s side vs the opener.\n')
    say('| market | model | games | toward / against | mean move, pts |')
    say('|---|---|---|---|---|')
    for kind, oc, pc in (('side', 'cbbd_open_spread', 'pt_cons_spread'), ('total', 'cbbd_open_total', 'pt_cons_total')):
        for m in ('A0', 'A1'):
            x = s[s[oc].notna() & s[pc].notna()].copy()
            x['gap'] = x[model_col(kind, m)] - v(kind, x[oc])
            x = x[x.gap.abs() >= THR[kind]]
            mv = np.sign(x.gap) * (v(kind, x[pc]) - v(kind, x[oc]))
            if len(x):
                say(f'| {"sides" if kind == "side" else "totals"} | {m} | {len(x)} | {(mv > 0).mean():.0%} / {(mv < 0).mean():.0%} '
                    f'| {mv.mean():+.2f} |')
    say('')


def main():
    s = load_all()
    say('# CBB frozen v1 shadow test — week-1 review\n')
    say('Freeze: commit cdacf27, cbb/models/frozen_v1.json. Pre-specified rules only (side edge >= 3, total edge >= 4; '
        'A0/A1/C1 as logged). One week of data: this checks logging and market movement; it is not a profitability test.\n')
    sec_quotes(s)
    sec_movement(s)
    sec_results(s)
    sec_opener(s)
    (HERE / 'shadow_review_week1.md').write_text('\n'.join(OUT) + '\n')
    print(f'\nSaved {HERE / "shadow_review_week1.md"}')


if __name__ == '__main__':
    main()
