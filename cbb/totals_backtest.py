"""CBB totals model: tune for TOTALS (not margin), then test vs closing totals and openers.

    python3 cbb/totals_backtest.py          # grid on 2022-25 by total MAE, holdout 2026 -> cbb/totals_report.md

Same discipline as the sides backtest: walk-forward only, tuned on accuracy (MAE vs actual total)
never on over/under record, 2026 untouched until the end.
What the totals version adds over the sides model:
  * lam3 / lamft: shooting luck. A team that hit 45% from three last week gets credit for its
    attempts at the league rate instead of its makes (lam=1), or a blend.
  * separate prior strengths for efficiency and tempo (k_prior / k_tempo), since pace is stickier.
"""
import itertools
import math
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import Params, load, read, walk_forward

HERE = Path(__file__).resolve().parent
TUNE, HOLD = [2022, 2023, 2024, 2025], [2026]
WIN = 100 / 110
OUT = []
G = None


def say(s=''):
    print(s, flush=True)
    OUT.append(s)


def lines():
    l = read('lines')
    t = l[l.overUnder.notna()].groupby('game_id').agg(tl=('overUnder', 'median'))
    o = l[l.overUnderOpen.notna()].groupby('game_id').agg(topen=('overUnderOpen', 'median'),
                                                          tclose=('overUnder', 'median'))
    return t, o


def run(p):
    pred, _ = walk_forward(G, p, seasons=set(TUNE + HOLD))
    d = pred.merge(G[['id', 'status', 'homePoints', 'awayPoints']].rename(columns={'id': 'game_id'}), on='game_id')
    d = d[d.status == 'final'].copy()
    d['actual'] = d.homePoints + d.awayPoints
    d['margin'] = d.homePoints - d.awayPoints
    return d


def score(args):
    p = Params(**args)
    d = run(p)
    t, _ = lines()
    d = d.merge(t, left_on='game_id', right_index=True)
    d = d[d.season.isin(TUNE)]
    return args, (d.actual - d.model_total).abs().mean(), (d.margin - d.model_margin).abs().mean()


def rec(side, res):
    r = np.sign(res * side)
    w, l = int((r > 0).sum()), int((r < 0).sum())
    n = w + l
    return f'{w}-{l} · {w / n * 100:.1f}% ±{math.sqrt(.25 / n) * 100:.1f} · {w * WIN - l:+.0f}u' if n else '—'


def report(d, label):
    e = d.model_total - d.tl
    say(f'\n## {label}: {len(d):,} games with a total\n')
    say(f'- MAE: model **{(d.actual - d.model_total).abs().mean():.2f}** vs line **{(d.actual - d.tl).abs().mean():.2f}**; '
        f'spread of projections: model sd {d.model_total.std():.1f} vs line sd {d.tl.std():.1f}')
    X = np.c_[np.ones(len(d)), d.tl, d.model_total]
    b, *_ = np.linalg.lstsq(X, d.actual, rcond=None)
    r = d.actual - X @ b
    se = np.sqrt(np.diag(r @ r / (len(d) - 3) * np.linalg.inv(X.T @ X)))
    say(f'- Information test (total ~ line + model): **model coef {b[2]:.3f} (t = {b[2] / se[2]:.1f})** -- '
        + ('model adds information beyond the line' if b[2] / se[2] > 2 else 'no reliable information beyond the line'))
    say('\n| edge | record | O/U ± 1 s.e. | units | share overs |')
    say('|---|---|---|---|---|')
    for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 9), (9, 99)):
        m = (e.abs() >= lo) & (e.abs() < hi)
        w = rec(np.sign(e[m]), (d.actual - d.tl)[m]).split(' · ')
        say(f'| {lo}–{hi if hi < 99 else "+"} | {w[0]} | {w[1] if len(w) > 1 else ""} | {w[2] if len(w) > 2 else ""} '
            f'| {np.mean(e[m] > 0) * 100:.0f}% |')


def open_test(d, o):
    y = d.merge(o, left_on='game_id', right_index=True)
    eo = y.model_total - y.topen
    side = np.sign(eo)
    clv = np.where(side > 0, y.tclose - y.topen, y.topen - y.tclose)
    say(f'\n## Against opening totals ({len(y):,} games, 2025-26)\n')
    say('| edge vs open | games | avg CLV | moved toward / against | O/U at open |')
    say('|---|---|---|---|---|')
    for lo in (0, 2, 4, 6, 9):
        m = (eo.abs() >= lo).values
        say(f'| ≥ {lo} | {m.sum():,} | {clv[m].mean():+.2f} | {np.mean(clv[m] > 0) * 100:.0f}% / {np.mean(clv[m] < 0) * 100:.0f}% '
            f'| {rec(side[m], (y.actual - y.topen)[m])} |')


def init():
    global G
    G = load(set(range(2021, 2027)))


def main():
    init()
    say('# CBB totals backtest\n')
    grid = [dict(lam3=a, lamft=b, k_prior=k, k_tempo=kt, carry=0.85)
            for a, b, k, kt in itertools.product([0, 0.5, 1.0], [0, 1.0], [6, 12], [6, 12])]
    with Pool(2, initializer=init) as pool:
        res = pool.map(score, grid)
    say('## Tuning grid (2022-25, by total MAE; side MAE shown for reference)\n')
    say('| lam3 | lamft | k_prior | k_tempo | total MAE | side MAE |')
    say('|---|---|---|---|---|---|')
    for a, tm, sm in sorted(res, key=lambda x: x[1]):
        say(f"| {a['lam3']} | {a['lamft']} | {a['k_prior']} | {a['k_tempo']} | {tm:.3f} | {sm:.3f} |")
    best = min(res, key=lambda x: x[1])[0]
    say(f'\nChosen for totals: {best}')
    d = run(Params(**best))
    t, o = lines()
    d = d.merge(t, left_on='game_id', right_index=True)
    report(d[d.season.isin(TUNE)], 'Tune seasons 2022–25')
    report(d[d.season.isin(HOLD)], 'Holdout 2026 (never used for tuning)')
    open_test(d, o)
    (HERE / 'totals_report.md').write_text('\n'.join(OUT) + '\n')
    print(f'\nSaved {HERE / "totals_report.md"}')


if __name__ == '__main__':
    main()
