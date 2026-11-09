"""Phase 2 CFB backtest on the CFBD Model Training Pack (2016-2025, closing spread) and the
Patreon Tier 3 weekly files (2026, opening spread).

The CFBD data is licensed for personal use: keep it OUT of this public repo (cfbd_pack/ is
git-ignored). Only code and aggregate results live here.

    python cfb_phase2/backtest_pack.py --hist <training_data_update.csv> --weekly-glob '<dir>/training_data_2026_week*.csv'

Conventions here: h = home margin (home - away); line = market's home margin = -spread.
Candidates (all predict h):
  ELO    ridge on Elo gap + home field (reference)
  STATS  ridge on pregame CFBD features (no market input)
  BLEND  line + w * (STATS - line), w from the out-of-season slope
  RESID  line + ridge(X -> h - line)   (market-anchored residual model)
Evaluation: leave-one-season-out over 2016-2024, then fit on 2016-2024 and test 2025 once.
"""
import argparse, glob, json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

PAIRS = [  # (home field, away field) -> home-minus-away "net" features
    ('adjusted_epa', 'adjusted_epa_allowed'), ('adjusted_rushing_epa', 'adjusted_rushing_epa_allowed'),
    ('adjusted_passing_epa', 'adjusted_passing_epa_allowed'), ('adjusted_success', 'adjusted_success_allowed'),
    ('adjusted_standard_down_success', 'adjusted_standard_down_success_allowed'),
    ('adjusted_passing_down_success', 'adjusted_passing_down_success_allowed'),
    ('adjusted_line_yards', 'adjusted_line_yards_allowed'), ('adjusted_explosiveness', 'adjusted_explosiveness_allowed'),
    ('points_per_opportunity_offense', 'points_per_opportunity_defense'),
    ('total_havoc_defense', 'total_havoc_offense'), ('avg_start_offense', 'avg_start_defense'),
]


def features(d):
    X = pd.DataFrame(index=d.index)
    X['hfa'] = (~d['neutral_site'].astype(bool)).astype(float)
    X['elo'] = d.home_elo - d.away_elo
    ht, at = d.home_talent.replace(0, np.nan), d.away_talent.replace(0, np.nan)
    X['talent'] = (ht - at)
    X['talent_missing'] = (ht.isna() | at.isna()).astype(float)
    for off, dfn in PAIRS:
        sign = 1
        X[off] = sign * ((d[f'home_{off}'] - d[f'home_{dfn}']) - (d[f'away_{off}'] - d[f'away_{dfn}']))
    # matchup split for the headline efficiency metric
    X['epa_home_off_vs_away_def'] = d.home_adjusted_epa - d.away_adjusted_epa_allowed
    X['epa_away_off_vs_home_def'] = d.away_adjusted_epa - d.home_adjusted_epa_allowed
    return X


class Ridge:
    def __init__(self, lam):
        self.lam = lam

    def fit(self, X, y):
        X = X.copy()
        self.med = X.median()
        X = X.fillna(self.med)
        self.mu, self.sd = X.mean(), X.std().replace(0, 1)
        Z = ((X - self.mu) / self.sd).values
        self.b0 = y.mean()
        self.b = np.linalg.solve(Z.T @ Z + self.lam * np.eye(Z.shape[1]), Z.T @ (y.values - self.b0))
        return self

    def predict(self, X):
        Z = ((X.fillna(self.med) - self.mu) / self.sd).values
        return self.b0 + Z @ self.b


def slope(pred, line, h, groups):
    """Slope of (h - line) on (pred - line) and a block-bootstrap SE over game-week groups."""
    x, y = (pred - line).values, (h - line).values
    b = np.polyfit(x, y, 1)[0]
    g = pd.Series(groups).values
    ug = np.unique(g)
    idx = {k: np.where(g == k)[0] for k in ug}
    rng = np.random.default_rng(0)
    bs = []
    for _ in range(400):
        s = np.concatenate([idx[k] for k in rng.choice(ug, len(ug))])
        if np.var(x[s]) > 0:
            bs.append(np.polyfit(x[s], y[s], 1)[0])
    return b, float(np.std(bs))


def ats(pred, line, h, thr):
    e = pred - line
    c = h - line
    m = (e.abs() >= thr) & (c != 0)
    w = (np.sign(e[m]) == np.sign(c[m])).sum()
    n = int(m.sum())
    return n, (w / n if n else np.nan), (w * 100 / 110 - (n - w)) if n else 0.0


def evaluate(df, cols, line_col='line', label=''):
    rows = []
    h, line = df.h, df[line_col]
    grp = df.season.astype(str) + '-' + df.week.astype(str)
    mkt_mse = ((h - line) ** 2)
    for c in cols:
        p = df[c]
        r = {'model': c, 'n': len(df), 'MAE': np.abs(p - h).mean(), 'RMSE': np.sqrt(((p - h) ** 2).mean())}
        d = ((p - h) ** 2) - mkt_mse
        wk = d.groupby(grp).mean()
        r['dMSE_vs_mkt'] = d.mean()
        r['dMSE_se'] = wk.std() / np.sqrt(len(wk)) * 1.0
        if c != line_col:
            r['slope'], r['slope_se'] = slope(p, line, h, grp)
            small = c in ('BLEND', 'RESID')
            for k, t in enumerate((0.5, 1, 1.5) if small else (3, 5, 7)):
                n, pct, u = ats(p, line, h, t)
                r[f'ATS_t{k + 1}'] = f'{pct:.3f} (n={n}, {u:+.1f}u, gap>={t})'
        rows.append(r)
    out = pd.DataFrame(rows)
    out.insert(0, 'sample', label)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist', required=True)
    ap.add_argument('--weekly-glob', required=True)
    ap.add_argument('--out', default=str(HERE / 'report.md'))
    a = ap.parse_args()

    raw = pd.read_csv(a.hist)
    d = raw[(raw.season_type == 'regular') & raw.spread.notna()].copy().reset_index(drop=True)
    d['h'] = -d['margin']            # pack: margin = away - home
    d['line'] = -d['spread']         # closing spread -> market home margin
    X = features(d)
    elo_cols = ['hfa', 'elo']
    stat_cols = list(X.columns)

    # ---- tune lambda by LOSO on 2016-2023, score on 2024 (validation) ------------------------
    lams = [10, 100, 300, 1000, 3000, 10000, 30000, 100000]
    tr = d.season <= 2023
    va = d.season == 2024
    tune = {}
    for lam in lams:
        m = Ridge(lam).fit(X[tr][stat_cols], d.h[tr])
        r = Ridge(lam).fit(X[tr][stat_cols], (d.h - d.line)[tr])
        tune[lam] = (np.abs(m.predict(X[va][stat_cols]) - d.h[va]).mean(),
                     np.abs(d.line[va] + r.predict(X[va][stat_cols]) - d.h[va]).mean())
    lam_s = min(tune, key=lambda k: tune[k][0])
    lam_r = min(tune, key=lambda k: tune[k][1])

    # ---- leave-one-season-out predictions, 2016-2024 ------------------------------------------
    dev = d[d.season <= 2024].copy()
    for c in ('ELO', 'STATS', 'RESID'):
        dev[c] = np.nan
    for s in sorted(dev.season.unique()):
        trn, tst = (dev.season != s), (dev.season == s)
        idx_tr, idx_te = dev.index[trn], dev.index[tst]
        dev.loc[tst, 'ELO'] = Ridge(1).fit(X.loc[idx_tr, elo_cols], d.h[idx_tr]).predict(X.loc[idx_te, elo_cols])
        dev.loc[tst, 'STATS'] = Ridge(lam_s).fit(X.loc[idx_tr, stat_cols], d.h[idx_tr]).predict(X.loc[idx_te, stat_cols])
        dev.loc[tst, 'RESID'] = d.line[idx_te] + Ridge(lam_r).fit(X.loc[idx_tr, stat_cols], (d.h - d.line)[idx_tr]).predict(X.loc[idx_te, stat_cols])
    w, w_se = slope(dev.STATS, dev.line, dev.h, dev.season.astype(str) + '-' + dev.week.astype(str))
    dev['BLEND'] = dev.line + w * (dev.STATS - dev.line)
    models = ['line', 'ELO', 'STATS', 'BLEND', 'RESID']
    res_dev = evaluate(dev, models, label='2016-24 LOSO')
    per_season = []
    for s_, g_ in dev.groupby('season'):
        b_, se_ = slope(g_.STATS, g_.line, g_.h, g_.week.astype(str))
        per_season.append({'season': s_, 'n': len(g_), 'STATS_MAE': np.abs(g_.STATS - g_.h).mean(),
                           'line_MAE': np.abs(g_.line - g_.h).mean(), 'slope_vs_close': b_, 'se': se_})
    per_season = pd.DataFrame(per_season)

    # ---- final fit on 2016-2024, test 2025 once ---------------------------------------------
    trn = d.season <= 2024
    tst = d.season == 2025
    te = d[tst].copy()
    m_elo = Ridge(1).fit(X[trn][elo_cols], d.h[trn])
    m_st = Ridge(lam_s).fit(X[trn][stat_cols], d.h[trn])
    m_rs = Ridge(lam_r).fit(X[trn][stat_cols], (d.h - d.line)[trn])
    te['ELO'] = m_elo.predict(X[tst][elo_cols])
    te['STATS'] = m_st.predict(X[tst][stat_cols])
    te['BLEND'] = te.line + w * (te.STATS - te.line)
    te['RESID'] = te.line + m_rs.predict(X[tst][stat_cols])
    res_test = evaluate(te, models, label='2025 test')

    # ---- 2026 prospective-style: fit on 2016-2025, apply to weekly files (opening line) -------
    all_tr = d.index
    f_st = Ridge(lam_s).fit(X.loc[all_tr, stat_cols], d.h[all_tr])
    f_rs = Ridge(lam_r).fit(X.loc[all_tr, stat_cols], (d.h - d.line)[all_tr])
    wk = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(a.weekly_glob))], ignore_index=True)
    wk = wk[wk.spread.notna()].copy()
    Xw = features(wk)
    wk['open_line'] = -wk['spread']
    wk['STATS'] = f_st.predict(Xw[stat_cols])
    wk['BLEND'] = wk.open_line + w * (wk.STATS - wk.open_line)
    wk['RESID'] = wk.open_line + f_rs.predict(Xw[stat_cols])
    graded = []
    for f in sorted((REPO / 'state' / 'graded').glob('week*_graded.csv')):
        graded.append(pd.read_csv(f))
    g = pd.concat(graded, ignore_index=True)
    lh = pd.read_csv(REPO / 'state' / 'line_history.csv').sort_values('logged_utc')
    first = lh.groupby('game_id').market_spread.first().rename('first_logged')
    j = wk.merge(g[['game_id', 'actual_margin', 'market_spread_home', 'close_spread_home', 'alpha_margin', 'beta_margin']],
                 left_on='id', right_on='game_id').merge(first, left_on='id', right_index=True, how='left')
    j['h'] = j.actual_margin
    j['board_line'] = -j.market_spread_home          # our Saturday grading line
    j['ALPHA'] = j.alpha_margin
    j['MIX'] = (j.ALPHA + j.STATS) / 2
    j['season'] = 2026
    res_26 = evaluate(j, ['open_line', 'board_line', 'ALPHA', 'STATS', 'MIX', 'BLEND', 'RESID'], line_col='open_line',
                      label='2026 wk6-9 vs opener')
    # line movement: opener -> our board line, toward each model?
    mv = []
    move = j.board_line - j.open_line
    for c in ('ALPHA', 'STATS', 'MIX', 'RESID'):
        e = j[c] - j.open_line
        nz = move != 0
        mv.append({'model': c, 'games': len(j), 'moves': int(nz.sum()),
                   'toward_model': float((np.sign(e[nz]) == np.sign(move[nz])).mean()),
                   'avg_clv_pts': float((np.sign(e) * move).mean()),
                   'slope_move_on_gap': float(np.polyfit(e, move, 1)[0]),
                   'corr': float(np.corrcoef(e, move)[0, 1])})
        if c in ('ALPHA', 'STATS', 'MIX'):
            big = e.abs() >= 4
            mv[-1]['avg_clv_pts_gap4+'] = float((np.sign(e[big]) * move[big]).mean()) if big.any() else None
            mv[-1]['n_gap4+'] = int(big.sum())
    gap_corr = float(np.corrcoef(j.ALPHA - j.open_line, j.STATS - j.open_line)[0, 1])
    mv = pd.DataFrame(mv)

    # ---- report -----------------------------------------------------------------------------
    coefs = pd.Series(m_st.b, index=stat_cols).sort_values(key=np.abs, ascending=False)
    rcoef = pd.Series(m_rs.b, index=stat_cols).sort_values(key=np.abs, ascending=False)
    fmt = lambda t: t.to_markdown(index=False, floatfmt='.3f')
    lines = [
        '# CFB Phase 2 — CFBD pack backtest', '',
        f'Data: {len(d)} regular-season games with a closing spread (2016-19, 2021-25); 2026 weekly files {len(wk)} games, {len(j)} with results (weeks 6-9).',
        f'Ridge lambda (tuned on 2024): STATS {lam_s}, RESID {lam_r}. Validation MAE by lambda (STATS, RESID): '
        + ', '.join(f'{k}: {v[0]:.2f}/{v[1]:.2f}' for k, v in tune.items()),
        f'BLEND weight w = out-of-season slope of (h - line) on (STATS - line) = {w:.3f} (se {w_se:.3f}).', '',
        'Benchmark in 2016-25 = CLOSING line (hardest, not bettable). Benchmark in 2026 = CFBD opening line.',
        'dMSE_vs_mkt < 0 means better than the market; se is over game-week blocks. ATS columns: games where |model - line| >= threshold.', '',
        '## 2016-2024, leave one season out', fmt(res_dev), '',
        '## STATS by season (out of season), slope vs the closing line', fmt(per_season), '',
        '## 2025 held-out test (fit on 2016-2024)', fmt(res_test), '',
        '## 2026 weeks 6-9 (fit on 2016-2025), graded vs the CFBD opener', fmt(res_26), '',
        '## 2026: did the line move from the opener toward the model by our Saturday board line?', fmt(mv), '',
        f'Correlation of ALPHA and STATS gaps to the opener (2026): {gap_corr:.3f}', '',
        '## STATS top coefficients (standardized, pts per 1 sd)', coefs.head(10).round(2).to_frame('coef').to_markdown(), '',
        '## RESID top coefficients (pts of h - line per 1 sd)', rcoef.head(10).round(2).to_frame('coef').to_markdown(), '',
    ]
    Path(a.out).write_text('\n'.join(lines))
    print('\n'.join(lines))
    json.dump({'lam_stats': lam_s, 'lam_resid': lam_r, 'blend_w': w, 'blend_w_se': w_se},
              open(HERE / 'params.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
