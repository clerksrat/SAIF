"""CBB efficiency ratings, fit walk-forward one day at a time.

Model (per team-game row, both teams of every final D1-vs-D1 game):
    points per 100 possessions = mu + O[team] - D[opponent] + h * loc      loc = +1 home, -1 away, 0 neutral
    possessions per 40 min     = tmu + T[team] + T[opponent]
fit by ridge regression that shrinks each team toward its PRIOR (last season's final rating,
regressed toward average by `carry`). `k_prior` is how many games that prior is worth, so
early-season ratings lean on last year and fade to this season's games as they pile up.

Prediction for a game:
    poss   = tmu + T[home] + T[away]
    margin = ((mu + O[h] - D[a] + h*loc) - (mu + O[a] - D[h] - h*loc)) * poss / 100
    total  = ((mu + O[h] - D[a] + h*loc) + (mu + O[a] - D[h] - h*loc)) * poss / 100
"""
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / 'data'
ET = ZoneInfo('America/New_York')


@dataclass
class Params:
    k_prior: float = 6.0      # prior worth this many games (efficiency)
    carry: float = 0.7        # share of last season's rating carried into this season
    k_tempo: float = 6.0      # prior worth this many games (tempo)
    k_league: float = 200.0   # mu / tmu / h shrink toward last season's values (rows)
    h_start: float = 2.5      # home edge, points per 100 poss, for the first season


def load():
    """Final D1-vs-D1 games with possessions; one row per game."""
    g = pd.read_csv(DATA / 'games.csv.gz')
    b = pd.read_csv(DATA / 'team_box.csv.gz', low_memory=False)
    g = g[g.homeConference.notna() & g.awayConference.notna()].copy()   # D1 only (non-D1 have no conference)
    g['date'] = pd.to_datetime(g.startDate, utc=True).dt.tz_convert(ET).dt.date
    est = (b.team_fieldGoals_attempted - b.team_rebounds_offensive + b.team_turnovers_total
           + 0.475 * b.team_freeThrows_attempted)
    b['poss'] = b.team_possessions.fillna(est)
    b['minutes'] = b.gameMinutes.fillna(40).clip(lower=40)
    pos = b.groupby('gameId').agg(poss=('poss', 'mean'), minutes=('minutes', 'max'))
    g = g.merge(pos, left_on='id', right_index=True, how='left')
    g['loc'] = np.where(g.neutralSite.fillna(False).astype(bool), 0, 1)
    return g.sort_values(['season', 'date', 'id']).reset_index(drop=True)


def market_lines():
    """One market spread per game: median across the books CBBD has for it (spread = HOME spread)."""
    l = pd.read_csv(DATA / 'lines.csv.gz')
    l = l[l.spread.notna()]
    agg = l.groupby('game_id').agg(spread=('spread', 'median'), total_line=('overUnder', 'median'),
                                   books=('provider', lambda s: ','.join(sorted(set(s)))))
    return agg


class Season:
    """Accumulates one season's games and re-solves the ratings on demand."""

    def __init__(self, teams, p: Params, prior=None):
        self.idx = {t: i for i, t in enumerate(teams)}
        n = self.n = len(teams)
        self.p = p
        prior = prior or {}
        O0 = np.array([prior.get('O', {}).get(t, 0.0) for t in teams]) * p.carry
        D0 = np.array([prior.get('D', {}).get(t, 0.0) for t in teams]) * p.carry
        T0 = np.array([prior.get('T', {}).get(t, 0.0) for t in teams]) * p.carry
        self.mu0, self.h0, self.tmu0 = prior.get('mu', 103.0), prior.get('h', p.h_start), prior.get('tmu', 68.0)
        # efficiency system: [O(n), D(n), mu, h]
        m = 2 * n + 2
        self.A = np.zeros((m, m))
        self.c = np.zeros(m)
        pen = np.r_[np.full(2 * n, p.k_prior), p.k_league, p.k_league]
        self.A[np.diag_indices(m)] += pen
        self.c += pen * np.r_[O0, D0, self.mu0, self.h0]
        # tempo system: [T(n), tmu]
        self.At = np.zeros((n + 1, n + 1))
        self.ct = np.zeros(n + 1)
        pent = np.r_[np.full(n, p.k_tempo), p.k_league]
        self.At[np.diag_indices(n + 1)] += pent
        self.ct += pent * np.r_[T0, self.tmu0]
        self.games = np.zeros(n)
        self.sol = None

    def add(self, home, away, hp, ap, poss, minutes, loc):
        if not np.isfinite(poss) or poss <= 0:
            return
        i, j, n = self.idx[home], self.idx[away], self.n
        for t, o, pts, l in ((i, j, hp, loc), (j, i, ap, -loc)):
            x = {t: 1.0, n + o: -1.0, 2 * n: 1.0, 2 * n + 1: float(l)}
            y = 100.0 * pts / poss
            for a, va in x.items():
                self.c[a] += va * y
                for b_, vb in x.items():
                    self.A[a, b_] += va * vb
        y = poss * 40.0 / minutes
        for a in (i, j, n):
            self.ct[a] += y
            for b_ in (i, j, n):
                self.At[a, b_] += 1.0
        self.games[i] += 1
        self.games[j] += 1
        self.sol = None

    def solve(self):
        if self.sol is None:
            e = np.linalg.solve(self.A, self.c)
            t = np.linalg.solve(self.At, self.ct)
            self.sol = (e, t)
        return self.sol

    def predict(self, home, away, loc):
        e, t = self.solve()
        n, i, j = self.n, self.idx[home], self.idx[away]
        mu, h = e[2 * n], e[2 * n + 1]
        poss = t[n] + t[i] + t[j]
        eh = mu + e[i] - e[n + j] + h * loc
        ea = mu + e[j] - e[n + i] - h * loc
        return (eh - ea) * poss / 100.0, (eh + ea) * poss / 100.0, poss

    def export(self):
        e, t = self.solve()
        n, teams = self.n, list(self.idx)
        return {'O': dict(zip(teams, e[:n])), 'D': dict(zip(teams, e[n:2 * n])), 'T': dict(zip(teams, t[:n])),
                'mu': e[2 * n], 'h': e[2 * n + 1], 'tmu': t[n]}


def walk_forward(games, p: Params, seasons=None):
    """Predict every game using only games finished on EARLIER dates. Returns one row per game."""
    out, prior = [], None
    for s, sg in games.groupby('season'):
        teams = sorted(set(sg.homeTeam) | set(sg.awayTeam))
        S = Season(teams, p, prior)
        for d, dg in sg.groupby('date', sort=True):
            if seasons is None or s in seasons:
                for r in dg.itertuples():
                    m, tot, poss = S.predict(r.homeTeam, r.awayTeam, r.loc)
                    out.append((r.id, s, d, r.homeTeam, r.awayTeam, r.loc, m, tot, poss,
                                S.games[S.idx[r.homeTeam]], S.games[S.idx[r.awayTeam]]))
            for r in dg[dg.status == 'final'].itertuples():
                S.add(r.homeTeam, r.awayTeam, r.homePoints, r.awayPoints, r.poss, r.minutes, r.loc)
        prior = S.export()
    return pd.DataFrame(out, columns=['game_id', 'season', 'date', 'home', 'away', 'loc', 'model_margin',
                                      'model_total', 'model_poss', 'home_games_before', 'away_games_before']), prior
