"""A2: roster-aware priors, point-in-time safe (review condition 2).

At season start every team keeps A0's prior (last season's rating x carry). From the first date a
team has played, its prior target is rebuilt from the players actually seen in its box scores on
EARLIER dates, using only last season's player minutes:

    O0(team) = a_ret  * sum over returning players   (share of team's minutes last season) * O_last(team)
             + a_tr   * sum over incoming D1 players (share of old team's minutes)        * O_last(old team)
             + a_prog * (1 - minutes share accounted for above)                           * O_last(team)
    (same for D)

The a_prog term covers minutes the box scores can't explain yet (freshmen, non-D1 transfers, players
who haven't appeared): they regress toward the PROGRAM's level, not the league average -- programs
replace good players with good players. Recruit ratings are a later step. No roster endpoint is used: a player only counts once he has appeared in a game
dated before the prediction. Injured returners who haven't played yet are therefore missed (known
limitation; it errs toward average, not toward last year).
"""
from zoneinfo import ZoneInfo

import pandas as pd

from ratings import DATA

ET = ZoneInfo('America/New_York')


def load_players(seasons):
    out = {}
    for s in seasons:
        f = DATA / f'players_{s}.csv.gz'
        if f.exists():
            p = pd.read_csv(f, usecols=['season', 'gameId', 'startDate', 'team', 'athleteId', 'minutes'])
            p['date'] = pd.to_datetime(p.startDate, utc=True, format='ISO8601').dt.tz_convert(ET).dt.date
            out[s] = p
    return out


class RosterPrior:
    def __init__(self, players, a_ret=1.0, a_tr=0.7, a_prog=0.7):
        self.players, self.a_ret, self.a_tr, self.a_prog = players, a_ret, a_tr, a_prog
        self.active = False

    def start(self, season, S, prior):
        self.S = S
        last, cur = self.players.get(season - 1), self.players.get(season)
        self.active = prior is not None and last is not None and cur is not None
        if not self.active:
            return
        self.O_last, self.D_last = prior['O'], prior['D']
        mins = last.groupby(['team', 'athleteId']).minutes.sum()
        share = mins / mins.groupby(level=0).transform('sum')
        self.share = share.to_dict()                                        # (team, athlete) -> share
        self.history = {}                                                   # athlete -> [(team, share)]
        for (t, a), sh in self.share.items():
            self.history.setdefault(a, []).append((t, sh))
        first = cur.groupby(['team', 'athleteId']).date.min().reset_index().sort_values('date')
        self.queue = list(first.itertuples(index=False, name=None))         # (team, athlete, date)
        self.pos = 0
        self.seen = {}

    def before(self, date, S):
        if not self.active:
            return
        changed = set()
        while self.pos < len(self.queue) and self.queue[self.pos][2] < date:
            t, a, _ = self.queue[self.pos]
            self.seen.setdefault(t, set()).add(a)
            changed.add(t)
            self.pos += 1
        for t in changed:
            if t not in S.idx:
                continue
            o = d = covered = 0.0
            for a in self.seen[t]:
                for u, sh in self.history.get(a, []):
                    if u not in self.O_last:
                        continue
                    w = self.a_ret if u == t else self.a_tr
                    o += w * sh * self.O_last[u]
                    d += w * sh * self.D_last[u]
                    covered += sh if u == t else min(sh * 1.0, 1.0)
            rest = max(0.0, 1.0 - covered)
            if t in self.O_last:
                o += self.a_prog * rest * self.O_last[t]
                d += self.a_prog * rest * self.D_last[t]
            S.set_prior(t, o, d)
