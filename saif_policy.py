"""SAIF CFB betting policy (Phase 1, adopted 2026-11-08). One place for the numbers.

Why (see claude/SAIF-Model-Diagnostics.md, revisit 2026-11-08): on weeks 6-9 the model's raw
edge carried only ~15% real information about the final margin (slope of actual-minus-line on
model-minus-line ~0.15), and the only positive signal was the line moving toward the model early
in the week. So:

  * Shrink:   SAIF projection = line + SHRINK_K * (Alpha margin - line)
              -> SAIF edge = SHRINK_K * raw Alpha edge.
  * Play:     |SAIF edge| >= PLAY_MIN at the ENTRY line. Flat 1 unit, -110.
  * Entry:    the first consensus (Odds API) line the board sees for a game, timestamped and
              locked in state/cfb_entries.csv. Never re-decided later in the week.
  * QB1:      a locked play on a team later flagged STALE (QB1 out, not in the model) is void.
  * Beta:     shadow only -- logged and graded, never a play.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SHRINK_K = 0.15
PLAY_MIN = 1.0          # shrunk points; equals a raw Alpha edge of ~6.7
UNIT = 1.0              # flat stake per play
ENTRIES_FILE = 'cfb_entries.csv'

ENTRY_COLS = ['game_id', 'week', 'home_team', 'away_team', 'kickoff_utc', 'locked_utc', 'lines_asof',
              'line_provider', 'entry_spread_home', 'best_home_spread', 'best_home_books',
              'best_away_spread', 'best_away_books', 'alpha_margin', 'beta_margin',
              'raw_edge', 'saif_edge', 'beta_saif_edge', 'play', 'pick']


def saif_edge(raw_edge):
    return SHRINK_K * raw_edge


def is_consensus(provider):
    return isinstance(provider, str) and provider.startswith('Consensus')


def load_entries(state_dir):
    f = Path(state_dir) / ENTRIES_FILE
    if not f.exists():
        return pd.DataFrame(columns=ENTRY_COLS)
    return pd.read_csv(f)


def lock_entries(wk, week, state_dir, now=None):
    """Lock an entry for every game that (a) has a consensus line, (b) hasn't kicked off,
    and (c) isn't locked yet. Returns (all entries, number newly locked)."""
    state_dir = Path(state_dir)
    now = pd.Timestamp.now(tz='UTC') if now is None else now
    ent = load_entries(state_dir)
    have = set(ent['game_id'].astype(int)) if len(ent) else set()
    new = []
    for r in wk.itertuples():
        gid = int(r.game_id)
        if gid in have or not is_consensus(getattr(r, 'line_provider', None)):
            continue
        if pd.isna(r.market_spread) or pd.Timestamp(r.kickoff_utc) <= now:
            continue
        raw = float(r.independent_edge)
        se = saif_edge(raw)
        play = abs(se) >= PLAY_MIN
        new.append({
            'game_id': gid, 'week': week, 'home_team': r.home_team, 'away_team': r.away_team,
            'kickoff_utc': pd.Timestamp(r.kickoff_utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'locked_utc': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'lines_asof': getattr(r, 'lines_asof', None), 'line_provider': r.line_provider,
            'entry_spread_home': float(r.market_spread),
            'best_home_spread': getattr(r, 'best_home_spread', np.nan),
            'best_home_books': getattr(r, 'best_home_books', ''),
            'best_away_spread': getattr(r, 'best_away_spread', np.nan),
            'best_away_books': getattr(r, 'best_away_books', ''),
            'alpha_margin': round(float(r.independent_margin), 3), 'beta_margin': round(float(r.beta_margin), 3),
            'raw_edge': round(raw, 3), 'saif_edge': round(se, 3),
            'beta_saif_edge': round(saif_edge(float(r.beta_edge)), 3),
            'play': bool(play), 'pick': ('home' if raw > 0 else 'away') if play else '',
        })
    if new:
        ent = pd.concat([ent, pd.DataFrame(new)[ENTRY_COLS]], ignore_index=True) if len(ent) else pd.DataFrame(new)[ENTRY_COLS]
        ent.to_csv(state_dir / ENTRIES_FILE, index=False)
    return ent, len(new)
