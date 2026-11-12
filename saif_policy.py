"""SAIF CFB betting policy. One place for the numbers. Version: POLICY_VERSION.

Why (claude/SAIF-Model-Diagnostics.md, revisit 2026-11-08; ChatGPT review 2026-11-08):
  * Shrink:   SAIF projection = line + SHRINK_K * (Alpha margin - line)
              -> SAIF edge = SHRINK_K * raw Alpha edge. NOTE: a constant shrink does not change
              which side or which games qualify -- PLAY_MIN 1.0 is the same as a raw gap >= 6.7.
              It is an experimental qualification rule, not a demonstrated edge.
  * Signal:   decided once, at the first consensus (Odds API) line the board sees (>= MIN_BOOKS books). Locked in
              state/cfb_entries.csv with a timestamp. Never re-decided.
  * Ticket:   the observed quote we would bet (a PAPER ticket unless placed): among EXEC_BOOKS quotes
              in the same pull that are fresh (<= QUOTE_MAX_AGE_MIN old at the pull) and priced inside
              [PRICE_MIN, PRICE_MAX], take the best number for the pick side, then the best price.
              No such quote -> 'no executable entry': kept as a signal, graded only in the consensus
              benchmark, excluded from executable results and CLV.
  * Placed:   placed_book / placed_point / placed_price are filled by hand for bets actually placed;
              graded separately.
  * Three result sets, never mixed: consensus benchmark (signal at consensus, -110), paper tickets,
              placed bets.
  * QB1:      judged ONLY with what was known at entry. A pick on a team flagged STALE (QB1 out)
              at entry is skipped. QB news after entry does not void the bet -- it is flagged.
  * Beta, Gamma: shadow only -- logged and graded, never a play. Gamma = cfb_phase2/gamma_frozen_v1.json.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

POLICY_VERSION = 'p1.3-2026-11-08'
SHRINK_K = 0.15
PLAY_MIN = 1.0          # shrunk points; equals a raw Alpha edge of ~6.7
UNIT = 1.0              # flat stake per play
EXEC_BOOKS = ('FanDuel', 'DraftKings', 'BetRivers')
PRICE_MIN, PRICE_MAX = -125, 115   # acceptable American price band for a ticket (frozen)
QUOTE_MAX_AGE_MIN = 90             # a book's quote must be at most this old at the pull
TRACKED_BANDS = {'band_1p5_3': (1.5, 3.0)}   # paper-only strategies on |raw Alpha edge| at the entry line (added 2026-11-12)
P4_CONFS = {'ACC', 'Big Ten', 'Big 12', 'SEC'}


def is_p4_conf_game(home_conf, away_conf):
    """Both teams in the same Power 4 conference (paper strategy band_1p5_3_p4conf, added 2026-11-12)."""
    return isinstance(home_conf, str) and home_conf == away_conf and home_conf in P4_CONFS


def in_band(raw_edge, key='band_1p5_3'):
    lo, hi = TRACKED_BANDS[key]
    return lo <= abs(raw_edge) < hi
MIN_BOOKS = 3           # consensus must cover at least this many books before an entry locks
ENTRIES_FILE = 'cfb_entries.csv'

ENTRY_COLS = ['game_id', 'week', 'home_team', 'away_team', 'kickoff_utc', 'locked_utc', 'lines_asof',
              'line_provider', 'n_books', 'entry_spread_home', 'best_home_spread', 'best_home_books',
              'best_away_spread', 'best_away_books', 'alpha_margin', 'beta_margin',
              'raw_edge', 'saif_edge', 'beta_saif_edge', 'qualifies', 'skip_reason', 'play', 'pick',
              'qb_home_flag_at_entry', 'qb_away_flag_at_entry',
              'exec_status', 'ticket_book', 'ticket_point', 'ticket_price', 'ticket_quote_utc',
              'consensus_raw_gap', 'ticket_raw_gap', 'ticket_saif_gap', 'exec_quotes',
              'placed_book', 'placed_point', 'placed_price',
              'gamma_margin', 'gamma_raw_gap', 'gamma_built_utc', 'home_conf', 'away_conf', 'policy_version']


def saif_edge(raw_edge):
    return SHRINK_K * raw_edge


def is_consensus(provider):
    return isinstance(provider, str) and provider.startswith('Consensus')


def flag(v):
    return v if isinstance(v, str) else ''


def load_entries(state_dir):
    f = Path(state_dir) / ENTRIES_FILE
    if not f.exists():
        return pd.DataFrame(columns=ENTRY_COLS)
    return pd.read_csv(f)


def pick_ticket(quotes_json, side, asof=None):
    """Best acceptable executable quote for `side` (points from the bettor's side, e.g. +7.5 / -3.0).
    Returns (ticket or None, text of every EXEC_BOOKS quote seen with its timestamp and why it was excluded)."""
    try:
        qs = json.loads(quotes_json) if isinstance(quotes_json, str) and quotes_json else []
    except ValueError:
        qs = []
    asof = pd.Timestamp(asof) if asof is not None and not (isinstance(asof, float) and np.isnan(asof)) else None
    cands, seen = [], []
    for q in qs:
        if q.get('book') not in EXEC_BOOKS or q.get(f'{side}_point') is None:
            continue
        pt, price, ts = float(q[f'{side}_point']), q.get(f'{side}_price'), q.get('last_update')
        why = ''
        try:
            pr = float(price)
        except (TypeError, ValueError):
            pr, why = np.nan, 'no price'
        if not why and not (PRICE_MIN <= pr <= -100 or 100 <= pr <= PRICE_MAX):
            why = 'price outside band'
        if not why and asof is not None and ts:
            age = (asof - pd.Timestamp(ts)).total_seconds() / 60
            if age > QUOTE_MAX_AGE_MIN:
                why = f'stale ({age:.0f} min)'
        seen.append(f"{q['book']} {pt:+.1f} ({price}) @{ts}" + (f' [{why}]' if why else ''))
        if not why:
            cands.append((pt, american_to_decimal(pr), q['book'], pr, ts))
    if not cands:
        return None, '; '.join(seen)
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    pt, _, book, price, ts = cands[0]
    return {'ticket_book': book, 'ticket_point': pt, 'ticket_price': price, 'ticket_quote_utc': ts}, '; '.join(seen)


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return np.nan
    return 1 + (a / 100 if a > 0 else 100 / -a)


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
        nb = getattr(r, 'odds_n_books', np.nan)
        if pd.notna(nb) and nb < MIN_BOOKS:
            continue   # too thin: wait for a later pull
        raw = float(r.independent_edge)
        se = saif_edge(raw)
        qualifies = abs(se) >= PLAY_MIN
        side = 'home' if raw > 0 else 'away'
        hf, af = flag(getattr(r, 'qb_home_flag', None)), flag(getattr(r, 'qb_away_flag', None))
        skip = ''
        if qualifies and ((side == 'home' and hf == 'STALE') or (side == 'away' and af == 'STALE')):
            skip = 'QB1 out at entry (model cannot see it)'
        ticket, exec_list = pick_ticket(getattr(r, 'book_quotes', ''), side, getattr(r, 'lines_asof', None))
        play = qualifies and not skip       # the SIGNAL; executability is exec_status
        model_side = float(r.independent_margin) if side == 'home' else -float(r.independent_margin)
        row = {
            'game_id': gid, 'week': week, 'home_team': r.home_team, 'away_team': r.away_team,
            'kickoff_utc': pd.Timestamp(r.kickoff_utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'locked_utc': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'lines_asof': getattr(r, 'lines_asof', None), 'line_provider': r.line_provider,
            'n_books': getattr(r, 'odds_n_books', np.nan),
            'entry_spread_home': float(r.market_spread),
            'best_home_spread': getattr(r, 'best_home_spread', np.nan),
            'best_home_books': getattr(r, 'best_home_books', ''),
            'best_away_spread': getattr(r, 'best_away_spread', np.nan),
            'best_away_books': getattr(r, 'best_away_books', ''),
            'alpha_margin': round(float(r.independent_margin), 3), 'beta_margin': round(float(r.beta_margin), 3),
            'raw_edge': round(raw, 3), 'saif_edge': round(se, 3),
            'beta_saif_edge': round(saif_edge(float(r.beta_edge)), 3),
            'qualifies': bool(qualifies), 'skip_reason': skip, 'play': bool(play), 'pick': side if qualifies else '',
            'qb_home_flag_at_entry': hf, 'qb_away_flag_at_entry': af,
            'exec_quotes': exec_list, 'policy_version': POLICY_VERSION,
            'consensus_raw_gap': round(abs(raw), 3),
            # Gamma shadow (never a play): its margin and gap to the same consensus entry line
            'gamma_margin': round(float(r.gamma_margin), 3) if pd.notna(getattr(r, 'gamma_margin', np.nan)) else np.nan,
            'gamma_raw_gap': round(float(r.gamma_margin) + float(r.market_spread), 3) if pd.notna(getattr(r, 'gamma_margin', np.nan)) else np.nan,
            'gamma_built_utc': getattr(r, 'gamma_built_utc', None),
            'home_conf': getattr(r, 'home_conference', None), 'away_conf': getattr(r, 'away_conference', None),
            'exec_status': ('paper ticket' if ticket else 'no executable entry') if play else '',
        }
        if play and ticket:
            row.update(ticket)
            row['ticket_raw_gap'] = round(model_side + ticket['ticket_point'], 3)   # model vs the ticket number
            row['ticket_saif_gap'] = round(SHRINK_K * row['ticket_raw_gap'], 3)
        new.append(row)
    if new:
        add = pd.DataFrame(new).reindex(columns=ENTRY_COLS)
        ent = pd.concat([ent.reindex(columns=ENTRY_COLS), add], ignore_index=True) if len(ent) else add
        ent.to_csv(state_dir / ENTRIES_FILE, index=False)
    return ent, len(new)
