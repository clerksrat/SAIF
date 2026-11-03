"""Backtest numbers for the CBB page -> cbb/models/backtest_summary.json.

    python3 cbb/backtest_summary.py      # ~1 min; rerun whenever SIDES / TOTALS settings change

Runs the production settings (ratings.SIDES and ratings.TOTALS) walk-forward over 2022-26 and
records, for sides and totals: accuracy vs the closing line (tuning seasons and the 2026 holdout)
and the open->close test by edge size (games, avg CLV, moved toward/against, record at the open).
The full write-ups stay in cbb/backtest_report.md and cbb/totals_report.md.
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import SIDES, TOTALS, load, read, walk_forward

HERE = Path(__file__).resolve().parent
TUNE, HOLD = [2022, 2023, 2024, 2025], [2026]
WIN = 100 / 110


def record(side, diff):
    r = np.sign(np.asarray(diff) * np.asarray(side))
    w, l, p = int((r > 0).sum()), int((r < 0).sum()), int((r == 0).sum())
    return {'w': w, 'l': l, 'p': p, 'pct': round(w / (w + l), 4) if w + l else None, 'units': round(w * WIN - l, 1)}


def predictions(p):
    g = load(set(range(2021, 2027)))
    pred, _ = walk_forward(g, p, seasons=set(TUNE + HOLD))
    d = pred.merge(g[['id', 'status', 'homePoints', 'awayPoints']].rename(columns={'id': 'game_id'}), on='game_id')
    d = d[d.status == 'final'].copy()
    d['margin'] = d.homePoints - d.awayPoints
    d['actual_total'] = d.homePoints + d.awayPoints
    return d


def lines():
    l = read('lines')
    close = l.groupby('game_id').agg(spread=('spread', 'median'), total=('overUnder', 'median'))
    opn = l[l.spreadOpen.notna() | l.overUnderOpen.notna()].groupby('game_id').agg(
        spread_open=('spreadOpen', 'median'), spread_close=('spread', 'median'),
        total_open=('overUnderOpen', 'median'), total_close=('overUnder', 'median'))
    return close, opn


def vs_close(d, kind):
    out = {}
    for label, seasons in (('tune', TUNE), ('holdout', HOLD)):
        x = d[d.season.isin(seasons)]
        if kind == 'sides':
            x = x[x.spread.notna()]
            edge, diff = x.model_margin + x.spread, x.margin + x.spread
            mae_m, mae_k = (x.margin - x.model_margin).abs().mean(), (x.margin + x.spread).abs().mean()
        else:
            x = x[x.total.notna()]
            edge, diff = x.model_total - x.total, x.actual_total - x.total
            mae_m, mae_k = (x.actual_total - x.model_total).abs().mean(), (x.actual_total - x.total).abs().mean()
        out[label] = {'seasons': f'{min(seasons)}-{max(seasons)}' if len(seasons) > 1 else str(seasons[0]),
                      'games': len(x), 'mae_model': round(mae_m, 2), 'mae_market': round(mae_k, 2),
                      'all': record(np.sign(edge), diff)}
    return out


def vs_open(d, kind, cuts):
    if kind == 'sides':
        x = d[d.spread_open.notna() & d.spread_close.notna()]
        e = x.model_margin + x.spread_open
        side = np.sign(e)
        clv = np.where(side > 0, x.spread_open - x.spread_close, x.spread_close - x.spread_open)
        diff = x.margin + x.spread_open
    else:
        x = d[d.total_open.notna() & d.total_close.notna()]
        e = x.model_total - x.total_open
        side = np.sign(e)
        clv = np.where(side > 0, x.total_close - x.total_open, x.total_open - x.total_close)
        diff = x.actual_total - x.total_open
    rows = []
    for lo in cuts:
        m = (e.abs() >= lo).values
        rows.append({'min_edge': lo, 'games': int(m.sum()), 'clv': round(float(clv[m].mean()), 2),
                     'toward': round(float((clv[m] > 0).mean()), 3), 'against': round(float((clv[m] < 0).mean()), 3),
                     **record(side[m], diff[m])})
    return {'seasons': sorted(int(s) for s in x.season.unique()), 'by_edge': rows}


def main():
    close, opn = lines()
    out = {'built': date.today().isoformat(), 'grading': 'flat -110; close = CBBD stored line (median across books)'}
    for kind, p, cuts in (('sides', SIDES, [0, 2, 3, 4, 6]), ('totals', TOTALS, [0, 2, 4, 6, 9])):
        d = predictions(p).merge(close, left_on='game_id', right_index=True, how='left') \
                          .merge(opn, left_on='game_id', right_index=True, how='left')
        out[kind] = {'params': {k: v for k, v in vars(p).items() if k in ('k_prior', 'carry', 'k_tempo', 'lam3')},
                     'vs_close': vs_close(d, kind), 'vs_open': vs_open(d, kind, cuts)}
        print(kind, json.dumps(out[kind]['vs_close']), flush=True)
    f = HERE / 'models' / 'backtest_summary.json'
    f.write_text(json.dumps(out, indent=1))
    print(f'Saved {f}')


if __name__ == '__main__':
    main()
