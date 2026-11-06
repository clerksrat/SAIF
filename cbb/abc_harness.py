"""A/B/C comparison harness (development run). Additive: the live model (A0) is untouched.

    python3 cbb/abc_harness.py            # -> cbb/abc_report.md   (~2-3 min)

Models (sides and totals, in "points" units: v = -spread for sides, v = total for totals):
  B   market opener (median across books with an opener). Primary benchmark.
  A0  production ratings (ratings.SIDES / ratings.TOTALS), unchanged.
  A1  A0 + calibration of the projection (sides: y ~ a*m + b*m|m|, fixes blowout compression;
      totals: y ~ c0 + c1*t) + uncertainty (sigma_rating, sigma_outcome).
  C   hybrid: opener + ridge on (A1 - opener) and its interactions with sigma_rating, line size,
      early season, conference game. C_out targets the final result, C_mkt targets the close.

Samples (same games for every paired comparison):
  A-dev   seasons 2017-2024, every game with a closing line. A1/A2 calibration and sigma fits use only
          EARLIER dev seasons (expanding window, and a rolling 3-season variant).
  A2      A1 machinery on projections with roster-aware priors (roster_prior.py; game-level player
          box scores only, point-in-time safe).
  BC-dev  games with an opener (Feb 2025 - Apr 2026). A1/A2 parameters are fit only on 2016-2024. C is fit with a rolling monthly origin: each test month uses only earlier months.
  2026 is development data (examined before); the untouched test is prospective 2027 shadow logging.

Uncertainty (documented assumptions, validated by interval coverage):
  sigma_rating^2 = (poss/100)^2 * sigma_e^2 * q, where q = g' A^-1 g from the ratings' normal equations
  (posterior covariance under the Gaussian reading of the ridge fit; see ratings.Season.var_terms).
  sigma_outcome^2 = sigma_rating^2 + s^2 * poss/70. sigma_e^2 and s^2 are fit by non-negative least
  squares of squared errors on [ (poss/100)^2 q , poss/70 ] in training data. Covariance between the
  two parts assumed zero.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import SIDES, TOTALS, load, read, walk_forward
from roster_prior import RosterPrior, load_players

HERE = Path(__file__).resolve().parent
A_DEV = list(range(2016, 2025))          # A development seasons (2015 is burn-in for the prior chain)
A2_SIDES = dict(a_ret=1.0, a_tr=0.7, a_prog=0.85)   # from the 2016-24 MAE grid (development)
A2_TOTALS = dict(a_ret=1.0, a_tr=0.7, a_prog=0.6)
FIRST_BC = '2025-02-01'
BOOT = 1000
RNG = np.random.default_rng(7)
WIN = 100 / 110
OUT = []


def say(s=''):
    print(s, flush=True)
    OUT.append(s)


def Phi(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x, float) / math.sqrt(2)))


# ------------------------------------------------------------------ data
def _wf(job):
    kind, roster = job
    g = load(set(range(2014, 2027)))
    p = SIDES if kind == 'side' else TOTALS
    hook = RosterPrior(load_players(range(2014, 2027)), **(A2_SIDES if kind == 'side' else A2_TOTALS)) if roster else None
    pred, _ = walk_forward(g, p, seasons=set(range(2015, 2027)), with_var=True, hook=hook)
    return job, pred


def build():
    from multiprocessing import Pool
    with Pool(2) as pool:
        res = dict(pool.map(_wf, [('side', False), ('total', False), ('side', True), ('total', True)]))
    g = load(set(range(2014, 2027)))
    ps, pt, ps2, pt2 = res[('side', False)], res[('total', False)], res[('side', True)], res[('total', True)]
    d = ps[['game_id', 'season', 'date', 'loc', 'model_margin', 'model_poss', 'q_margin',
            'home_games_before', 'away_games_before']].merge(
        pt[['game_id', 'model_total', 'q_total', 'model_poss']].rename(columns={'model_poss': 'poss_t'}), on='game_id')
    d = d.merge(ps2[['game_id', 'model_margin', 'q_margin']].rename(columns={'model_margin': 'a2_margin', 'q_margin': 'a2_qm'}), on='game_id')
    d = d.merge(pt2[['game_id', 'model_total', 'q_total']].rename(columns={'model_total': 'a2_total', 'q_total': 'a2_qt'}), on='game_id')
    d = d.merge(g[['id', 'status', 'homePoints', 'awayPoints', 'conferenceGame', 'startDate']]
                .rename(columns={'id': 'game_id'}), on='game_id')
    d = d[d.status == 'final'].copy()
    d['margin'] = d.homePoints - d.awayPoints
    d['total_pts'] = d.homePoints + d.awayPoints
    l = read('lines', set(range(2015, 2027)))
    agg = lambda x: x.groupby('game_id').agg(close=('spread', 'median'), open=('spreadOpen', 'median'),
                                             tclose=('overUnder', 'median'), topen=('overUnderOpen', 'median'),
                                             hml=('homeMoneyline', 'median'), aml=('awayMoneyline', 'median'))
    for tag, sub in (('', l), ('_bov', l[l.provider == 'Bovada']),
                     ('_nodk', l[~l.provider.isin(['Draft Kings', 'ESPN BET'])])):
        d = d.merge(agg(sub).add_suffix(tag), left_on='game_id', right_index=True, how='left')
    d['early'] = (np.minimum(d.home_games_before, d.away_games_before) < 5).astype(float)
    d['conf'] = d.conferenceGame.fillna(False).astype(float)
    d['month'] = d.startDate.str[:7]
    return d


def kind_frame(d, kind, tag=''):
    """Common columns: y, v_open, v_close, pred_A0, q, poss."""
    if kind == 'side':
        k = pd.DataFrame({'y': d.margin, 'v_open': -d['open' + tag], 'v_close': -d['close' + tag],
                          'pred_A0': d.model_margin, 'q': d.q_margin, 'poss': d.model_poss,
                          'pred_A2raw': d.a2_margin, 'q2': d.a2_qm})
    else:
        k = pd.DataFrame({'y': d.total_pts, 'v_open': d['topen' + tag], 'v_close': d['tclose' + tag],
                          'pred_A0': d.model_total, 'q': d.q_total, 'poss': d.poss_t,
                          'pred_A2raw': d.a2_total, 'q2': d.a2_qt})
    for c in ('game_id', 'season', 'date', 'month', 'early', 'conf', 'hml', 'aml'):
        k[c] = d[c].values
    return k


# ------------------------------------------------------------------ A1 pieces
def fit_cal(tr, kind, src='pred_A0'):
    m = tr[src].values
    X = np.c_[m, m * np.abs(m)] if kind == 'side' else np.c_[np.ones(len(m)), m]
    return np.linalg.lstsq(X, tr.y.values, rcond=None)[0]


def apply_cal(df, coef, kind, src='pred_A0'):
    m = df[src].values
    return coef[0] * m + coef[1] * m * np.abs(m) if kind == 'side' else coef[0] + coef[1] * m


def fit_sigma(tr, pred, qcol='q'):
    e2 = (tr.y - pred) ** 2
    X = np.c_[(tr.poss / 100) ** 2 * tr[qcol], tr.poss / 70]
    from numpy.linalg import lstsq
    coef = lstsq(X, e2, rcond=None)[0]
    return np.clip(coef, 1e-6, None)        # [sigma_e^2, s^2]


def sigmas(df, sc, qcol='q'):
    sr = np.sqrt(sc[0] * (df.poss / 100) ** 2 * df[qcol])
    return sr, np.sqrt(sr ** 2 + sc[1] * df.poss / 70)


VARIANTS = {'A1': ('pred_A0', 'q', 'pred_A1', 'sig_r', 'sig_o'),
            'A2': ('pred_A2raw', 'q2', 'pred_A2', 'sig_r2', 'sig_o2')}


def add_A(k, kind, train_mask, which='A1'):
    src, qcol, out, sr, so = VARIANTS[which]
    coef = fit_cal(k[train_mask], kind, src)
    k[out] = apply_cal(k, coef, kind, src)
    sc = fit_sigma(k[train_mask], k.loc[train_mask, out], qcol)
    k[sr], k[so] = sigmas(k, sc, qcol)
    return coef, sc


def add_A1(k, kind, train_mask):
    return add_A(k, kind, train_mask, 'A1')


# ------------------------------------------------------------------ C (rolling monthly origin)
def c_features(k, pred='pred_A1', simple=False):
    dlt = k[pred] - k.v_open
    if simple:
        return np.c_[np.ones(len(k)), dlt]
    return np.c_[np.ones(len(k)), dlt, dlt * k.sig_r, dlt * np.abs(k.v_open) / 10, dlt * k.early, dlt * k.conf]


def ridge(X, y, lam=50.0):
    P = lam * np.eye(X.shape[1])
    P[0, 0] = 0
    return np.linalg.solve(X.T @ X + P, X.T @ y)


def add_C(bc, min_train=1000):
    bc = bc.sort_values('date').copy()
    for c in ('pred_C', 'pred_Cmkt', 'pred_C1'):
        bc[c] = np.nan
    for mo in sorted(bc.month.unique()):
        tr, te = bc[bc.month < mo], bc.month == mo
        if len(tr) < min_train:
            continue
        Xtr, Xte = c_features(tr), c_features(bc[te])
        bo = ridge(Xtr, (tr.y - tr.v_open).values)
        bm = ridge(Xtr, (tr.v_close - tr.v_open).values)
        bc.loc[te, 'pred_C'] = bc.loc[te, 'v_open'] + Xte @ bo
        bc.loc[te, 'pred_Cmkt'] = bc.loc[te, 'v_open'] + Xte @ bm
        b1 = ridge(c_features(tr, simple=True), (tr.y - tr.v_open).values)       # C1: opener + one shrink weight
        bc.loc[te, 'pred_C1'] = bc.loc[te, 'v_open'] + c_features(bc[te], simple=True) @ b1
    return bc


# ------------------------------------------------------------------ metrics
def block_boot(df, stat, n=BOOT):
    """95% CI of stat(df) resampling whole dates."""
    dates = df.date.unique()
    groups = {dt: ix for dt, ix in df.groupby('date').indices.items()}
    vals = []
    for _ in range(n):
        pick = RNG.choice(dates, len(dates))
        idx = np.concatenate([groups[dt] for dt in pick])
        vals.append(stat(df.iloc[idx]))
    return np.percentile(vals, [2.5, 97.5])


def outcome_rows(k, models):
    say('| model | MAE | RMSE | ΔMSE vs B (95% CI) |')
    say('|---|---|---|---|')
    for m in models:
        e = k.y - k[m]
        if m == 'v_open':
            dm = ''
        else:
            stat = lambda x, m=m: ((x.y - x[m]) ** 2 - (x.y - x.v_open) ** 2).mean()
            lo, hi = block_boot(k, stat, 400)
            dm = f'{stat(k):+.2f} ({lo:+.2f} to {hi:+.2f})'
        say(f'| {label(m)} | {e.abs().mean():.3f} | {np.sqrt((e ** 2).mean()):.3f} | {dm} |')
    say(f'| close (market benchmark) | {(k.y - k.v_close).abs().mean():.3f} | {np.sqrt(((k.y - k.v_close) ** 2).mean()):.3f} | |')


def label(m):
    return {'v_open': 'B (opener)', 'pred_A0': 'A0 (live)', 'pred_A1': 'A1', 'pred_A2': 'A2 (rosters)', 'pred_C': 'C (full)', 'pred_C1': 'C1 (opener + one weight)',
            'pred_Cmkt': 'C (close-targeted)'}.get(m, m)


def market_rows(k, models):
    say('| model | slope of (close−open) on (model−open) | t | MAE predicting the close |')
    say('|---|---|---|---|')
    say(f'| B (opener) | — | — | {(k.v_close - k.v_open).abs().mean():.3f} |')
    for m in models:
        x = (k[m] - k.v_open).values
        yv = (k.v_close - k.v_open).values
        b = (x @ yv) / (x @ x)
        res = yv - b * x
        se = math.sqrt((res @ res) / (len(x) - 1) / (x @ x))
        say(f'| {label(m)} | {b:.3f} | {b / se:.1f} | {(k.v_close - k[m]).abs().mean():.3f} |')


def bets(k, m, thr, fill='open', shift=0.0):
    edge = k[m] - k.v_open
    sel = k[edge.abs() >= thr].copy()
    side = np.sign(edge[edge.abs() >= thr])
    line = sel.v_open if fill == 'open' else (sel.v_open + sel.v_close) / 2
    line = line + side * shift                       # shift > 0: line moved against us before we bet
    res = np.sign((sel.y - line) * side)
    clv = side * (sel.v_close - sel.v_open)
    sel['res'], sel['clv'] = res.values, clv.values
    return sel


def econ(sel):
    w, l = int((sel.res > 0).sum()), int((sel.res < 0).sum())
    units = w * WIN - l
    roi = units / max(w + l, 1)
    s = sel.sort_values('date')
    pnl = np.where(s.res > 0, WIN, np.where(s.res < 0, -1.0, 0.0)).cumsum()
    dd = float((np.maximum.accumulate(np.r_[0, pnl]) - np.r_[0, pnl]).max())
    return w, l, units, roi, dd


def econ_rows(k, models, thr):
    say(f'| model | bets | toward / against | avg CLV | record | units | ROI (95% CI) | max drawdown | ROI at mid fill | ROI −0.5 |')
    say('|---|---|---|---|---|---|---|---|---|---|')
    for m in models:
        sel = bets(k, m, thr)
        if len(sel) < 30:
            say(f'| {label(m)} | {len(sel)} | too few bets | | | | | | | |')
            continue
        w, l, units, roi, dd = econ(sel)
        lo, hi = block_boot(sel, lambda x: econ(x)[3], 400)
        mid = econ(bets(k, m, thr, fill='mid'))[3]
        sh = econ(bets(k, m, thr, shift=0.5))[3]
        say(f'| {label(m)} | {len(sel)} | {(sel.clv > 0).mean():.0%} / {(sel.clv < 0).mean():.0%} | {sel.clv.mean():+.2f} '
            f'| {w}-{l} ({w / max(w + l, 1):.1%}) | {units:+.1f}u | {roi:+.1%} ({lo:+.1%} to {hi:+.1%}) | {dd:.1f}u '
            f'| {mid:+.1%} | {sh:+.1%} |')


def logistic_slope(z, y, iters=25):
    """Slope b of logit P(y=1) = a + b*z (Newton). 1 = well calibrated; < 1 = overconfident."""
    X = np.c_[np.ones(len(z)), z]
    w = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        H = X.T @ (X * (p * (1 - p))[:, None]) + 1e-9 * np.eye(2)
        w += np.linalg.solve(H, X.T @ (y - p))
    return w[1]


def calib_rows(k, models):
    say('| model | log loss (cover at opener) | Brier | calibration slope | 50% / 80% / 90% interval coverage |')
    say('|---|---|---|---|---|')
    push = k.y == k.v_open
    kk = k[~push]
    yb = (kk.y > kk.v_open).astype(float).values
    say(f'| B (opener, p = 0.5) | {math.log(2):.4f} | 0.2500 | — | — |')
    for m in models:
        so = 'sig_o2' if m == 'pred_A2' else 'sig_o'
        p = np.clip(Phi((kk[m] - kk.v_open) / kk[so]), 1e-4, 1 - 1e-4)
        ll = -np.mean(yb * np.log(p) + (1 - yb) * np.log(1 - p))
        br = np.mean((p - yb) ** 2)
        z = np.log(p / (1 - p))
        slope = logistic_slope(z, yb)
        cov = [np.mean(np.abs(k.y - k[m]) <= q * k[so]) for q in (0.674, 1.282, 1.645)]
        say(f'| {label(m)} | {ll:.4f} | {br:.4f} | {slope:.2f} | {cov[0]:.0%} / {cov[1]:.0%} / {cov[2]:.0%} |')


def spearman(a, b):
    return pd.Series(a).rank().corr(pd.Series(b).rank())


def uncertainty_test(bc):
    """Does |edge| / sqrt(sigma_r^2 + tau^2) rank closing-line movement better than |edge|? tau fit on early months."""
    k = bc.dropna(subset=['pred_A1'])
    edge = k.pred_A1 - k.v_open
    toward = np.sign(edge) * (k.v_close - k.v_open)
    months = sorted(k.month.unique())
    split = months[len(months) // 2]
    tr, te = k.month < split, k.month >= split
    taus = [0.25, 0.5, 1, 2, 3, 5, 8]
    best = max(taus, key=lambda t: spearman((edge.abs() / np.sqrt(k.sig_r ** 2 + t ** 2))[tr], toward[tr]))
    z = edge.abs() / np.sqrt(k.sig_r ** 2 + best ** 2)
    say(f'Train months < {split}, test months ≥ {split}. τ chosen on train: {best}')
    say(f'- Spearman with movement toward the model, test months: |edge| {spearman(edge.abs()[te], toward[te]):.3f} '
        f'vs stabilized ratio {spearman(z[te], toward[te]):.3f} (n = {int(te.sum())})')
    X = np.c_[np.ones(int(te.sum())), edge.abs()[te], k.sig_r[te], (edge.abs() * k.sig_r)[te]]
    yv = toward[te].values
    b = np.linalg.lstsq(X, yv, rcond=None)[0]
    r = yv - X @ b
    se = np.sqrt(np.diag(r @ r / (len(yv) - 4) * np.linalg.inv(X.T @ X)))
    say(f'- Regression on test months, movement toward model ~ |edge| + σ_rating + |edge|×σ_rating: '
        + ', '.join(f'{n} {bb:+.3f} (t {bb / s:.1f})' for n, bb, s in zip(['const', '|edge|', 'σ_r', '|edge|×σ_r'], b, se)))


def win_prob_vs_ml(k):
    """A1 win probability vs de-vigged closing moneyline (sides only)."""
    x = k.dropna(subset=['hml', 'aml'])
    x = x[(x.y != 0)]
    imp = lambda ml: np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    ph, pa = imp(x.hml), imp(x.aml)
    pm = ph / (ph + pa)
    pa1 = np.clip(Phi(x.pred_A1 / x.sig_o), 1e-4, 1 - 1e-4)
    yw = (x.y > 0).astype(float)
    ll = lambda p: -np.mean(yw * np.log(np.clip(p, 1e-4, 1 - 1e-4)) + (1 - yw) * np.log(np.clip(1 - p, 1e-4, 1 - 1e-4)))
    say(f'- Win probability, {len(x):,} games with closing moneylines: log loss A1 {ll(pa1):.4f} vs market (de-vigged) {ll(pm):.4f}')


# ------------------------------------------------------------------ run
def section(d, kind):
    name = 'Sides' if kind == 'side' else 'Totals'
    thr = 3.0 if kind == 'side' else 4.0
    k = kind_frame(d, kind)
    say(f'\n# {name}\n')

    # A-dev: rolling-origin calibration (each season fit only on EARLIER dev seasons), every game with a close
    a_all = k[k.season.isin(A_DEV) & k.v_close.notna()].copy()
    variants = {}
    for wname, win in (('expanding', None), ('rolling 3', 3)):
        parts = []
        for s_ in A_DEV[1:]:
            tmp = a_all.copy()
            prev = [x for x in A_DEV if x < s_]
            prev = prev if win is None else prev[-win:]
            mask = tmp.season.isin(prev).values
            add_A(tmp, kind, mask, 'A1')
            add_A(tmp, kind, mask, 'A2')
            parts.append(tmp[tmp.season == s_])
        variants[wname] = pd.concat(parts)
    a = variants['expanding']
    say(f'## A-dev {A_DEV[1]}–{A_DEV[-1]} ({len(a):,} games; calibration fit only on earlier seasons)\n')
    say('Outcome accuracy vs the CLOSE (no openers in these seasons):\n')
    say('| model | MAE | RMSE | MAE early season | MAE later |')
    say('|---|---|---|---|---|')
    ea = a.early == 1
    rows_ = [('pred_A0', 'A0 (live)', a), ('pred_A1', 'A1, expanding window', a), ('pred_A1', 'A1, rolling 3 seasons', variants['rolling 3']),
             ('pred_A2', 'A2 (rosters), expanding', a), ('pred_A2', 'A2 (rosters), rolling 3', variants['rolling 3'])]
    for m, lab, frame in rows_:
        e = frame.y - frame[m]
        say(f'| {lab} | {e.abs().mean():.3f} | {np.sqrt((e ** 2).mean()):.3f} | {e[ea].abs().mean():.3f} | {e[~ea].abs().mean():.3f} |')
    e = a.y - a.v_close
    say(f'| close (market benchmark) | {e.abs().mean():.3f} | {np.sqrt((e ** 2).mean()):.3f} | {e[ea].abs().mean():.3f} | {e[~ea].abs().mean():.3f} |')
    for m, so in (('pred_A2', 'sig_o2'),):
        cov2 = [np.mean(np.abs(a.y - a[m]) <= q * a[so]) for q in (0.674, 1.282, 1.645)]
        say(f'\n- A2 interval coverage (target 50 / 80 / 90%): {cov2[0]:.0%} / {cov2[1]:.0%} / {cov2[2]:.0%}')
    cov = [np.mean(np.abs(a.y - a.pred_A1) <= q * a.sig_o) for q in (0.674, 1.282, 1.645)]
    say(f'- A1 interval coverage (target 50 / 80 / 90%): {cov[0]:.0%} / {cov[1]:.0%} / {cov[2]:.0%}')
    early = a.early == 1
    say(f'- σ_outcome early season (a team < 5 games) {a.sig_o[early].mean():.1f} vs later {a.sig_o[~early].mean():.1f}; '
        f'σ_rating {a.sig_r[early].mean():.1f} vs {a.sig_r[~early].mean():.1f}')
    for lo, hi in ((0, 10), (10, 20), (20, 99)):
        mm = (a.v_close.abs() >= lo) & (a.v_close.abs() < hi) if kind == 'side' else None
        if mm is not None:
            say(f'- |close| {lo}-{hi if hi < 99 else "+"}: mean signed error A0 {((a.y - a.pred_A0) * np.sign(a.v_close))[mm].mean():+.2f}, '
                f'A1 {((a.y - a.pred_A1) * np.sign(a.v_close))[mm].mean():+.2f}, close {((a.y - a.v_close) * np.sign(a.v_close))[mm].mean():+.2f} '
                f'(positive = favorite did better than projected)')
    if kind == 'side':
        win_prob_vs_ml(a)

    # BC-dev: games with openers; A1 fit only on seasons before 2025
    bc = k[(k.date.astype(str) >= FIRST_BC) & k.v_open.notna() & k.v_close.notna()].copy()
    pre = k[k.season.isin(A_DEV) & k.v_close.notna()].copy()
    coef = fit_cal(pre, kind)
    bc['pred_A1'] = apply_cal(bc, coef, kind)
    sc = fit_sigma(pre, apply_cal(pre, coef, kind))
    bc['sig_r'], bc['sig_o'] = sigmas(bc, sc)
    coef2 = fit_cal(pre, kind, 'pred_A2raw')
    bc['pred_A2'] = apply_cal(bc, coef2, kind, 'pred_A2raw')
    sc2 = fit_sigma(pre, apply_cal(pre, coef2, kind, 'pred_A2raw'), 'q2')
    bc['sig_r2'], bc['sig_o2'] = sigmas(bc, sc2, 'q2')
    bc = add_C(bc)
    t = bc.dropna(subset=['pred_C', 'pred_C1'])
    say(f'\n## BC-dev: games with an opener ({len(bc):,}; C scored on {len(t):,} from {t.month.min()} on, rolling monthly origin)\n')
    say(f'A1 calibration (fit on {A_DEV[0]}–{A_DEV[-1]}): {np.round(coef, 4).tolist()} | σ_e² {sc[0]:.1f}, s² {sc[1]:.1f}; '
        f'A2: {np.round(coef2, 4).tolist()}\n')
    models = ['v_open', 'pred_A0', 'pred_A1', 'pred_A2', 'pred_C', 'pred_C1']
    say('**1. Final outcomes** (identical games)\n')
    outcome_rows(t, models)
    say('\n**2. Closing-line movement**\n')
    market_rows(t, ['pred_A0', 'pred_A1', 'pred_A2', 'pred_C', 'pred_C1', 'pred_Cmkt'])
    say('\n**3. Probability calibration** (cover at the opener; intervals for the final result)\n')
    calib_rows(t, ['pred_A1', 'pred_A2', 'pred_C', 'pred_C1'])
    say(f'\n**4. Betting economics at the opener**, edge ≥ {thr:g} (threshold carried over from earlier work, not re-tuned here), −110\n')
    econ_rows(t, ['pred_A0', 'pred_A1', 'pred_A2', 'pred_C', 'pred_C1'], thr)
    say('\n*C weights by test month (C1: share of the model−opener gap kept):* '
        + ', '.join(f'{mo} {((x.pred_C1 - x.v_open) / (x.pred_A1 - x.v_open).replace(0, np.nan)).median():.2f}'
                    for mo, x in t.groupby('month')))
    say('\n**5. Uncertainty test** (reported separately; not a profitability claim)\n')
    uncertainty_test(bc)

    say('\n**Sensitivity: benchmark book choice** (outcome MAE of B and A1 on the same games)\n')
    say('| opener source | games | B MAE | A1 MAE | close MAE |')
    say('|---|---|---|---|---|')
    for tag, lab in (('', 'median of all books'), ('_bov', 'Bovada only'), ('_nodk', 'excluding DraftKings / ESPN BET')):
        kk = kind_frame(d, kind, tag)
        x = kk[(kk.date.astype(str) >= FIRST_BC) & kk.v_open.notna() & kk.v_close.notna()].copy()
        x['pred_A1'] = apply_cal(x, coef, kind)
        say(f'| {lab} | {len(x):,} | {(x.y - x.v_open).abs().mean():.3f} | {(x.y - x.pred_A1).abs().mean():.3f} '
            f'| {(x.y - x.v_close).abs().mean():.3f} |')


def main():
    say('# CBB A/B/C harness — development run\n')
    say('Development data only. 2026 was examined earlier and is not a holdout; promotion requires the prospective '
        '2027 shadow test and the pre-registered rule in SAIF-CBB-ABC-Design.md.')
    d = build()
    for kind in ('side', 'total'):
        section(d, kind)
    (HERE / 'abc_report.md').write_text('\n'.join(OUT) + '\n')
    print(f'\nSaved {HERE / "abc_report.md"}')


if __name__ == '__main__':
    main()
