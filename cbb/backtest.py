"""CBB walk-forward backtest.

    python3 cbb/backtest.py            # tune on 2022-25, report tune seasons + 2026 holdout
    python3 cbb/backtest.py --no-tune  # skip the parameter grid, use Params() defaults

Discipline:
  * Every prediction uses only games finished on earlier dates (ratings.walk_forward).
  * Parameters are chosen by MODEL ACCURACY (MAE vs actual margin) on 2022-25, never by ATS
    record -- ATS is what we're testing, so it can't also be what we tune on.
  * 2026 (last season) is a holdout: it plays no part in choosing anything.
  * Graded against the stored CBBD spread (median across books on file), which is a late /
    near-closing number, at flat -110.
Writes cbb/backtest_report.md and cbb/data/backtest_predictions.csv.gz.
"""
import argparse
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import DATA, Params, load, market_lines, read, walk_forward

HERE = Path(__file__).resolve().parent
TUNE = [2022, 2023, 2024, 2025]
HOLDOUT = [2026]
WIN = 100 / 110
BUCKETS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 99)]
PLAY = 2.0          # |edge| at or above this counts as a "play" for the split tables
OUT = []


def say(s=''):
    print(s, flush=True)
    OUT.append(s)


def build(p):
    g = load()
    pred, _ = walk_forward(g, p, seasons=set(TUNE + HOLDOUT))
    d = pred.merge(g[['id', 'status', 'homePoints', 'awayPoints', 'conferenceGame', 'seasonType']]
                   .rename(columns={'id': 'game_id'}), on='game_id')
    d = d.merge(market_lines(), left_on='game_id', right_index=True, how='left')
    d = d[(d.status == 'final') & d.spread.notna()].copy()
    d['margin'] = d.homePoints - d.awayPoints
    d['market_margin'] = -d.spread
    return d


def grade(d, edge_col='edge'):
    """W/L/P for betting the side the edge points to. edge > 0 -> home."""
    cover = d.margin + d.spread
    side = np.sign(d[edge_col])
    res = np.sign(cover * side)
    return pd.Series(np.where(side == 0, np.nan, res), index=d.index)


def rec(r):
    r = r.dropna()
    w, l, p = int((r > 0).sum()), int((r < 0).sum()), int((r == 0).sum())
    n = w + l
    pct = w / n if n else float('nan')
    se = math.sqrt(.25 / n) if n else float('nan')
    return w, l, p, pct, w * WIN - l, se


def fmt(r):
    w, l, p, pct, u, se = rec(r)
    if w + l == 0:
        return '—'
    return f'{w}-{l}-{p} | {pct*100:.1f}% ±{se*100:.1f} | {u:+.1f}u'


def info_test(d):
    """OLS: actual margin ~ a + b*market + c*model. c > 0 (with t > 2) = the model knows
    something the line doesn't. Also the best blend weight of model vs market."""
    X = np.c_[np.ones(len(d)), d.market_margin, d.model_margin]
    y = d.margin.values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (len(y) - 3)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return beta, se


def table(d, title, groups):
    say(f'\n**{title}** (plays: |edge| ≥ {PLAY})\n')
    say('| | record | ATS ± 1 s.e. | units |')
    say('|---|---|---|---|')
    for name, mask in groups:
        x = d[mask & (d.edge.abs() >= PLAY)]
        w, l, p, pct, u, se = rec(x.res)
        if w + l:
            say(f'| {name} | {w}-{l}-{p} | {pct*100:.1f}% ±{se*100:.1f} | {u:+.1f}u |')


def report(d, label):
    say(f'\n## {label}: {len(d):,} games with a line\n')
    mae_m, mae_k = (d.margin - d.model_margin).abs().mean(), (d.margin - d.market_margin).abs().mean()
    say(f'- MAE: model **{mae_m:.2f}** vs market **{mae_k:.2f}** (market better by {mae_m - mae_k:.2f})')
    beta, se = info_test(d)
    say(f'- Information test (margin ~ market + model): market coef {beta[1]:.2f}, '
        f'**model coef {beta[2]:.3f} (t = {beta[2]/se[2]:.1f})** -- '
        + ('model adds information beyond the line' if beta[2] / se[2] > 2 else
           'no reliable information beyond the line'))
    say(f'- All games, side the model prefers: {fmt(d.res)}  (break-even 52.4%)')
    say('\n| edge | record | ATS ± 1 s.e. | units |')
    say('|---|---|---|---|')
    for lo, hi in BUCKETS:
        x = d[(d.edge.abs() >= lo) & (d.edge.abs() < hi)]
        w, l, p, pct, u, se_ = rec(x.res)
        say(f'| {lo}–{hi if hi < 99 else "+"} | {w}-{l}-{p} | {pct*100:.1f}% ±{se_*100:.1f} | {u:+.1f}u |')
    home_pick = d.edge > 0
    line_for_pick = np.where(home_pick, d.spread, -d.spread)
    month = pd.to_datetime(d.date).dt.month
    early = np.minimum(d.home_games_before, d.away_games_before) < 5
    table(d, 'Splits', [
        ('Home pick', home_pick), ('Away pick', ~home_pick),
        ('Favorite pick', line_for_pick < 0), ('Underdog pick', line_for_pick > 0),
        ('Conference game', d.conferenceGame.fillna(False).astype(bool)),
        ('Non-conference', ~d.conferenceGame.fillna(False).astype(bool)),
        ('Early (a team has < 5 games)', early), ('Later', ~early),
        ('Neutral site', d['loc'] == 0), ('Postseason', d.seasonType == 'postseason')])
    table(d, 'By month', [(m, month == n) for m, n in
                          (('Nov', 11), ('Dec', 12), ('Jan', 1), ('Feb', 2), ('Mar', 3), ('Apr', 4))])
    table(d, 'By season', [(str(s), d.season == s) for s in sorted(d.season.unique())])


def open_test(d):
    """Seasons with opening lines (2025 ESPN BET partial, 2026 Bovada/DK/ESPN): edge vs the OPENER,
    then did the line move toward the model (CLV) and how did it do ATS at the opener."""
    l = read('lines')
    l = l[l.spread.notna() & l.spreadOpen.notna()]
    o = l.groupby('game_id').agg(open=('spreadOpen', 'median'), close=('spread', 'median'))
    x = d.merge(o, left_on='game_id', right_index=True)
    x['edge_open'] = x.model_margin + x.open
    say(f'\n## Against opening lines ({len(x):,} games, seasons {sorted(int(v) for v in x.season.unique())})\n')
    say('CLV = points the line moved toward the model\u2019s side between open and close.\n')
    say('| edge vs open | games | avg CLV | beat close / moved against | ATS at open |')
    say('|---|---|---|---|---|')
    for lo in (0, 1, 2, 3, 4, 6):
        y = x[x.edge_open.abs() >= lo]
        side = np.sign(y.edge_open)
        clv = np.where(side > 0, y.open - y.close, y.close - y.open)
        res = np.sign((y.margin + y.open) * side)
        w, l_, p_, pct, u, se = rec(pd.Series(res))
        say(f'| ≥ {lo} | {len(y):,} | {clv.mean():+.2f} | {np.mean(clv > 0)*100:.0f}% / {np.mean(clv < 0)*100:.0f}% '
            f'| {w}-{l_} {pct*100:.1f}% ±{se*100:.1f} |')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-tune', action='store_true')
    ap.add_argument('--k-prior', type=float, default=6)
    ap.add_argument('--carry', type=float, default=0.85)
    a = ap.parse_args()
    say('# CBB backtest — efficiency ratings vs the market\n')
    best = Params(k_prior=a.k_prior, carry=a.carry, k_tempo=a.k_prior)
    if not a.no_tune:
        say('## Tuning (2022-25, by model MAE only)\n')
        say('| k_prior | carry | model MAE |')
        say('|---|---|---|')
        scores = []
        for k, c in itertools.product([3, 6, 10, 16], [0.5, 0.7, 0.85]):
            p = Params(k_prior=k, carry=c, k_tempo=k)
            d = build(p)
            d = d[d.season.isin(TUNE)]
            mae = (d.margin - d.model_margin).abs().mean()
            scores.append((mae, k, c))
            say(f'| {k} | {c} | {mae:.3f} |')
        _, k, c = min(scores)
        best = Params(k_prior=k, carry=c, k_tempo=k)
    say(f'\nChosen: k_prior={best.k_prior}, carry={best.carry}\n')
    d = build(best)
    d['edge'] = d.model_margin + d.spread          # > 0: model likes home
    d['res'] = grade(d)
    d.to_csv(DATA / 'backtest_predictions.csv.gz', index=False)
    report(d[d.season.isin(TUNE)], 'Tune seasons 2022–25')
    report(d[d.season.isin(HOLDOUT)], 'Holdout 2026 (never used for tuning)')
    open_test(d)
    (HERE / 'backtest_report.md').write_text('\n'.join(OUT) + '\n')
    print(f'\nSaved {HERE / "backtest_report.md"}')


if __name__ == '__main__':
    main()
