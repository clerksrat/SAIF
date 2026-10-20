"""Use The Odds API as the board's market line (consensus across US books), CFBD as fallback.

saif_pull_all.py saves the raw feed to  cfb_fullseason_data_<season>/odds_api/raw_odds.json.
apply_odds_lines(wk, data_dir) matches those games to the board's CFBD games and, where matched:
    market_spread      <- consensus home spread (most common number across books; ties -> nearest the median)
    cfbd_spread        <- the CFBD line it replaced (kept for reference)
    best_home_spread   <- best number for a home-side bettor (the largest home spread on offer)
    best_away_spread   <- best number for an away-side bettor, written from the AWAY side (e.g. +17.0)
    best_home_books / best_away_books <- which sportsbooks offer that best number (e.g. "FanDuel, BetMGM")
    odds_n_books, line_provider ("Consensus (N books)"), lines_asof (UTC timestamp of the pull)
and recomputes both models' edges against the new line. Unmatched games keep their CFBD line.
"""
import json
import re
import statistics
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

# CFBD name -> other spellings The Odds API may use (school part only; mascots are handled by prefix match)
ALIASES = {
    'App State': ['appalachian state'], 'Southern Miss': ['southern mississippi'],
    'Sam Houston': ['sam houston state'], 'UL Monroe': ['louisiana monroe', 'ul monroe'],
    'Louisiana': ['louisiana lafayette', 'ul lafayette'], 'Massachusetts': ['umass'],
    'UConn': ['connecticut'], 'Florida International': ['fiu'], 'NC State': ['north carolina state'],
    'UTSA': ['ut san antonio'], 'UTEP': ['ut el paso'], 'Miami': ['miami fl', 'miami florida'],
    'Miami (OH)': ['miami ohio'], 'Middle Tennessee': ['middle tennessee state'],
    "Hawai'i": ['hawaii'], 'Southern California': ['usc'],
    'Central Florida': ['ucf'], 'Kennesaw State': ['kennesaw st'],
}
MAX_KICKOFF_GAP_H = 6


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    s = s.lower().replace('&', '')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def name_ok(cfbd, odds):
    o = norm(odds)
    return any(o == c or o.startswith(c + ' ') for c in [norm(cfbd)] + ALIASES.get(cfbd, []))


def consensus(points):
    counts = Counter(points)
    top = max(counts.values())
    modes = [p for p, n in counts.items() if n == top]
    med = statistics.median(points)
    return min(modes, key=lambda p: (abs(p - med), p))


def book_list(names, show=2):
    names = sorted(set(names))
    return ', '.join(names[:show]) + (f' +{len(names) - show} more' if len(names) > show else '')


def odds_games(data_dir):
    f = data_dir / 'odds_api' / 'raw_odds.json'
    if not f.exists():
        return [], None
    raw = json.loads(f.read_text(encoding='utf-8'))
    out = []
    for g in raw.get('data', []):
        home = g.get('home_team')
        pts, books = [], []
        for bk in g.get('bookmakers', []):
            for m in bk.get('markets', []):
                if m.get('key') != 'spreads':
                    continue
                for o in m.get('outcomes', []):
                    if o.get('name') == home and o.get('point') is not None:
                        pts.append(float(o['point']))
                        books.append(bk.get('title') or bk.get('key') or '?')
        if pts:
            out.append({'home': home, 'away': g.get('away_team'), 'time': pd.Timestamp(g['commence_time']),
                        'pts': pts, 'books': books})
    return out, raw.get('retrieved_at_utc')


def apply_odds_lines(wk, data_dir):
    games, asof = odds_games(data_dir)
    wk = wk.copy()
    wk['cfbd_spread'] = wk['market_spread']
    for c in ('best_home_spread', 'best_away_spread', 'odds_n_books'):
        wk[c] = np.nan
    wk['best_home_books'] = ''
    wk['best_away_books'] = ''
    wk['lines_asof'] = asof
    if not games:
        print('[lines] no Odds API data found -- using CFBD lines for every game')
        return wk
    matched, unmatched = 0, []
    for i, r in wk.iterrows():
        k = pd.Timestamp(r.kickoff_utc)
        k = k.tz_localize('UTC') if k.tzinfo is None else k
        cands = []
        for g in games:
            gap = abs((g['time'] - k).total_seconds()) / 3600
            if gap > MAX_KICKOFF_GAP_H:
                continue
            if name_ok(r.home_team, g['home']) and name_ok(r.away_team, g['away']):
                cands.append((gap, 1, g))
            elif name_ok(r.home_team, g['away']) and name_ok(r.away_team, g['home']):
                cands.append((gap, -1, g))   # listed the other way round (neutral site): flip the sign
        if not cands:
            unmatched.append(f'{r.away_team} at {r.home_team}')
            continue
        cands.sort(key=lambda t: t[0])
        if len(cands) > 1 and cands[0][0] == cands[1][0]:
            unmatched.append(f'{r.away_team} at {r.home_team} (ambiguous)')
            continue
        _, sign, g = cands[0]
        pts = [sign * p for p in g['pts']]
        wk.at[i, 'market_spread'] = consensus(pts)
        wk.at[i, 'best_home_spread'] = max(pts)        # home bettor wants the biggest number
        wk.at[i, 'best_away_spread'] = -min(pts)       # away bettor's line, from the away side
        wk.at[i, 'best_home_books'] = book_list([b for p, b in zip(pts, g['books']) if p == max(pts)])
        wk.at[i, 'best_away_books'] = book_list([b for p, b in zip(pts, g['books']) if p == min(pts)])
        wk.at[i, 'odds_n_books'] = len(pts)
        wk.at[i, 'line_provider'] = f'Consensus ({len(pts)} books)'
        matched += 1
    wk['independent_edge'] = wk['independent_margin'] + wk['market_spread']
    wk['beta_edge'] = wk['beta_margin'] + wk['market_spread']
    moved = int((wk['market_spread'] - wk['cfbd_spread']).abs().gt(0.01).sum())
    print(f'[lines] Odds API consensus used for {matched} of {len(wk)} games (pulled {asof}); '
          f'{moved} differ from the CFBD line')
    if unmatched:
        print('[lines] kept CFBD line (no Odds API match): ' + '; '.join(unmatched))
    return wk
