"""Freeze v1: fit and save every parameter the prospective shadow test uses, then never refit in-season.

    python3 cbb/freeze.py      # -> cbb/models/frozen_v1.json   (~3 min; run once, then tag the commit)

Fitted on development data only (through April 2026):
  A1   projection calibration + sigma (sigma_e^2, s^2), sides and totals, on 2016-2026 closes.
  C1   opener + w * (A1 - opener) + b, sides and totals, on all opener games Feb 2025 - Apr 2026.
  Probability recalibration (review item 3): cover probability at the opener,
       logit p = a + b * logit(p_raw), p_raw = Phi((A1 - opener) / sigma_outcome).
       Fit chronologically on Feb 2025 - Dec 2025 opener games, audited on Jan - Apr 2026
       (audit numbers stored), then refit on all of them for the frozen value.
Nothing here changes the live board (A0).
"""
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

import abc_harness as H

HERE = Path(__file__).resolve().parent


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def platt(z, y, iters=50):
    X = np.c_[np.ones(len(z)), z]
    w = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        H_ = X.T @ (X * (p * (1 - p))[:, None]) + 1e-9 * np.eye(2)
        w += np.linalg.solve(H_, X.T @ (y - p))
    return w


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main():
    d = H.build()
    out = {'version': 'v1', 'built': date.today().isoformat(), 'data_through': '2026-04', 'kinds': {}}
    for kind in ('side', 'total'):
        k = H.kind_frame(d, kind)
        dev = k[k.season.isin(range(2016, 2027)) & k.v_close.notna()].copy()
        coef = H.fit_cal(dev, kind)
        sc = H.fit_sigma(dev, H.apply_cal(dev, coef, kind))
        bc = k[(k.date.astype(str) >= H.FIRST_BC) & k.v_open.notna() & k.v_close.notna()].copy()
        bc['pred_A1'] = H.apply_cal(bc, coef, kind)
        bc['sig_r'], bc['sig_o'] = H.sigmas(bc, sc)
        dlt = (bc.pred_A1 - bc.v_open).values
        X = np.c_[np.ones(len(bc)), dlt]
        c1 = H.ridge(X, (bc.y - bc.v_open).values)
        # probability recalibration: chronological fit + audit, then full refit
        bc = bc[bc.y != bc.v_open]
        yb = (bc.y > bc.v_open).astype(float).values
        z = logit(H.Phi((bc.pred_A1 - bc.v_open) / bc.sig_o))
        tr = (bc.month < '2026-01').values
        w_tr = platt(z[tr], yb[tr])
        p_raw, p_cal = 1 / (1 + np.exp(-z[~tr])), 1 / (1 + np.exp(-(w_tr[0] + w_tr[1] * z[~tr])))
        audit = {'train_months': '2025-02..2025-12', 'test_months': '2026-01..2026-04', 'n_test': int((~tr).sum()),
                 'logloss_raw': round(ll(p_raw, yb[~tr]), 4), 'logloss_recal': round(ll(p_cal, yb[~tr]), 4),
                 'logloss_coinflip': round(math.log(2), 4), 'slope_after_recal': round(float(platt(
                     np.log(np.clip(p_cal, 1e-4, 1 - 1e-4) / (1 - np.clip(p_cal, 1e-4, 1 - 1e-4))), yb[~tr])[1]), 3),
                 'recal_fit_on_train': [round(float(v), 4) for v in w_tr]}
        w_all = platt(z, yb)
        out['kinds'][kind] = {'A1_calibration': [float(v) for v in coef], 'A1_sigma': {'sigma_e2': float(sc[0]), 's2': float(sc[1])},
                              'C1': {'intercept': float(c1[0]), 'weight': float(c1[1])},
                              'prob_recal': {'a': float(w_all[0]), 'b': float(w_all[1])}, 'prob_recal_audit': audit}
        print(kind, json.dumps(out['kinds'][kind], indent=1))
    f = HERE / 'models' / 'frozen_v1.json'
    f.write_text(json.dumps(out, indent=1))
    print(f'Saved {f}')


if __name__ == '__main__':
    main()
