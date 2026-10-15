"""QB1 availability flags for the SAIF board (Gamma groundwork -- flags only, no margin adjustment).

Backtest 2023-25 (2,104 games): market already prices a known QB1 absence (-0.2 +/- 0.7 pts),
but Alpha/Beta rate teams on season-to-date stats that still include QB1, so on the FIRST game
he misses their number is stale. Rule:
  QB1 = most pass attempts so far this season (>= MIN_ATT attempts, >= MIN_GAMES games).
  missed = consecutive most-recent team games with 0 QB1 attempts (byes don't count).
  STALE  : QB1 listed Out/Doubtful (SportsDataIO) or missed exactly 1 game, and missed < 2
           -> models can't see it; a pick on that team is muted.
  PRICED : missed >= 2 -> stats have mostly caught up; info chip only.
  WATCH  : listed Questionable, played last game -> info chip only.
"""
import json, re
from pathlib import Path
import pandas as pd

MIN_ATT, MIN_GAMES = 40, 2
BAD = {'Out', 'Doubtful'}
norm = lambda s: re.sub('[^a-z]', '', (s or '').lower())


def load_box(box_dir, season):
    rows = []
    for f in sorted(Path(box_dir).glob(f'passing_{season}_w*.json')):
        wk = int(re.search(r'_w(\d+)', f.name).group(1))
        for g in json.load(open(f)):
            for t in g.get('teams', []):
                for c in t.get('categories', []):
                    for ty in c.get('types', []):
                        if ty['name'] == 'C/ATT':
                            for a in ty['athletes']:
                                try:
                                    rows.append((wk, t['team'], str(a['id']), a['name'], int(a['stat'].split('/')[1])))
                                except (ValueError, IndexError):
                                    pass
    return pd.DataFrame(rows, columns=['week', 'team', 'pid', 'name', 'att'])


def team_status(P, team, week, inj_qbs):
    """Return (flag, text) for one team, or (None, '')."""
    d = P[(P.team == team) & (P.week < week)]
    if d.empty:
        return None, ''
    cum = d.groupby(['pid', 'name']).att.sum().sort_values(ascending=False)
    (pid, name), att = cum.index[0], cum.iloc[0]
    weeks = sorted(d.week.unique())
    if att < MIN_ATT or len(weeks) < MIN_GAMES:
        return None, ''
    played = set(d[(d.pid == pid) & (d.att > 0)].week)
    missed = 0
    for w in reversed(weeks):
        if w in played:
            break
        missed += 1
    status = inj_qbs.get(norm(name))
    if missed >= 2:
        return 'PRICED', f'QB1 {name} out {missed} straight games (already in team stats)'
    if status in BAD or missed == 1:
        why = f'listed {status}' if status in BAD else 'missed last game'
        return 'STALE', f'QB1 {name} {why}; models still rate the team with him'
    if status == 'Questionable':
        return 'WATCH', f'QB1 {name} listed Questionable'
    return None, ''


def injury_qb_map(inj, team):
    if not inj:
        return {}
    tid = inj['cross'].get(team)
    return {norm(f"{p['FirstName']} {p['LastName']}"): p['InjuryStatus']
            for p in inj['players'] if tid and p['TeamID'] == tid and p.get('Position') == 'QB'}


def flag_board(wk, box_dir, season, week, inj):
    P = load_box(box_dir, season)
    for side in ('home', 'away'):
        res = [team_status(P, t, week, injury_qb_map(inj, t)) if not P.empty else (None, '')
               for t in wk[f'{side}_team']]
        wk[f'qb_{side}_flag'] = [r[0] for r in res]
        wk[f'qb_{side}_note'] = [r[1] for r in res]
    return wk, (not P.empty)
