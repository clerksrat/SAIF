"""Grade a week's SAIF board against final scores.

Usage (from the saif_local folder, same place you run build_board.py):
    python grade_week.py 6
    python grade_week.py 6 --season 2026

Reads  state/week{N}_scored.pkl   (the frozen board: model margins + lines at pull time)
Fetches final scores from CFBD /games (needs CFBD_API_KEY in .env or the environment)
Writes state/graded/week{N}_graded.csv  (one row per completed game)
       state/graded/summary.csv         (one row per graded week, replaced on rerun)

W/L uses the line stored on the board at the last pull (the entry line). CLV compares that
entry line with the closing snapshot in state/closing_lines.csv (snapshot_close.py), in points
for the side picked: positive = you got a better number than the close. Standard flat -110 payout (win +0.909, loss -1).
Convention: market_spread is the HOME spread (negative = home favored); a positive edge
means the model likes the home side. Home covers when actual_margin + market_spread > 0.
"""
import argparse, json, math, os, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
import pandas as pd

HERE = Path(__file__).resolve().parent
WIN_PAYOUT = 100 / 110


def load_env_file(path=HERE / '.env'):
    """Read KEY=value lines from .env beside this script (real environment variables win).
    Tolerates UTF-8 BOM / UTF-16 (PowerShell and Notepad write these), 'export ' prefixes and quotes."""
    if not Path(path).exists():
        print(f'[env] no .env found at {path} -- using environment variables only', flush=True)
        return
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-16'):
        try:
            text = raw.decode(enc)
            if '=' in text:
                break
        except UnicodeError:
            continue
    else:
        text = raw.decode('utf-8', 'ignore')
    found = []
    for line in text.splitlines():
        line = line.strip().lstrip('\ufeff')
        if line.lower().startswith('export '):
            line = line[7:].strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key, value)
            found.append(key)
    print(f'[env] loaded {path.name if hasattr(path, "name") else path}: keys found = {found or "NONE"}', flush=True)

def fetch_finals(season, week):
    key = os.environ.get('CFBD_API_KEY', '').strip()
    if not key:
        raise SystemExit('CFBD_API_KEY not set (put it in .env next to this script).')
    url = 'https://api.collegefootballdata.com/games?' + urlencode(
        {'year': season, 'week': week, 'seasonType': 'regular'})
    req = Request(url, headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    for attempt in range(5):   # CFBD throws the odd 502; back off and retry
        try:
            with urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8'))
        except HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise SystemExit(f'CFBD HTTP {e.code} fetching week {week} finals.') from None
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2 ** attempt)
    raise SystemExit(f'CFBD unreachable after retries fetching week {week} finals.')


def load_closes(state):
    """Closing lines from snapshot_close.py: list of (home, away, kickoff, snapshot, close_spread_home)."""
    f = state / 'closing_lines.csv'
    if not f.exists():
        return []
    c = pd.read_csv(f)
    c['commence_time'] = pd.to_datetime(c['commence_time'], utc=True)
    c['snapshot_utc'] = pd.to_datetime(c['snapshot_utc'], utc=True)
    c = c[c.snapshot_utc <= c.commence_time]
    return list(c[['home_team', 'away_team', 'commence_time', 'snapshot_utc', 'close_spread_home']]
                .itertuples(index=False, name=None))


def closing_spread(closes, home, away, kickoff):
    """Last pre-kick snapshot for this game, as a HOME spread (sign flipped if the feed lists it reversed)."""
    from odds_lines import name_ok, MAX_KICKOFF_GAP_H
    k = pd.Timestamp(kickoff)
    k = k.tz_localize('UTC') if k.tzinfo is None else k
    best = None
    for h, a, t, snap, sp in closes:
        if abs((t - k).total_seconds()) / 3600 > MAX_KICKOFF_GAP_H:
            continue
        sign = 1 if name_ok(home, h) and name_ok(away, a) else -1 if name_ok(home, a) and name_ok(away, h) else 0
        if sign and (best is None or snap > best[0]):
            best = (snap, sign * sp)
    return None if best is None else best[1]


def clv_points(pick, entry_home, close_home):
    """Points of CLV for the side picked. Home bettor wants a bigger home spread at entry than at close."""
    if pick is None or close_home is None:
        return None
    return round((entry_home - close_home) if pick == 'home' else (close_home - entry_home), 2)


def grade_side(edge, cover_margin):
    """edge>0 -> pick home. Returns (pick, result, units)."""
    if edge is None or (isinstance(edge, float) and math.isnan(edge)) or edge == 0:
        return None, None, None
    pick = 'home' if edge > 0 else 'away'
    c = cover_margin if pick == 'home' else -cover_margin
    if c > 0:
        return pick, 'W', WIN_PAYOUT
    if c < 0:
        return pick, 'L', -1.0
    return pick, 'P', 0.0


P4 = {'ACC', 'Big Ten', 'Big 12', 'SEC'}
G5 = {'American Athletic', 'Conference USA', 'Mid-American', 'Mountain West', 'Sun Belt'}


def conf_map():
    f = HERE / 'models' / 'cfbd_conferences_2022-2025.csv'
    if not f.exists():
        return {}
    c = pd.read_csv(f)
    return c[c.season == 2025].set_index('team')['conference'].to_dict()


def tier_of(conf):
    return 'P4' if conf in P4 else 'G5' if conf in G5 else 'other'


def matchup_tier(hc, ac):
    h, a = tier_of(hc), tier_of(ac)
    if h == 'other' or a == 'other':
        return 'OTHER'
    return 'P4vP4' if h == a == 'P4' else 'G5vG5' if h == a == 'G5' else 'CROSS'


def bucket(e):
    a = abs(e)
    return '<2' if a < 2 else '2-4' if a < 4 else '4-7' if a < 7 else '7+'


def summarize(df, tag, edge_col):
    g = df[df[f'{tag}_result'].isin(['W', 'L', 'P'])]
    w, l, p = (g[f'{tag}_result'] == x for x in 'WLP')
    n_dec = int(w.sum() + l.sum())
    units = float(g[f'{tag}_units'].sum())
    return {
        'model': tag, 'games': len(g), 'W': int(w.sum()), 'L': int(l.sum()), 'P': int(p.sum()),
        'ats_pct': round(w.sum() / n_dec * 100, 1) if n_dec else None,
        'units_flat_110': round(units, 2),
        'roi_pct': round(units / len(g) * 100, 1) if len(g) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('week', type=int)
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--state-dir', default=str(HERE / 'state'))
    ap.add_argument('--finals-json', help='offline: use a saved CFBD /games JSON instead of the API')
    a = ap.parse_args()

    load_env_file()
    state = Path(a.state_dir)
    pkl = state / f'week{a.week}_scored.pkl'
    if not pkl.exists():
        raise SystemExit(f'{pkl} not found -- run build_board.py for week {a.week} first.')
    board = pd.read_pickle(pkl)

    games = json.load(open(a.finals_json)) if a.finals_json else fetch_finals(a.season, a.week)
    fin = {}
    for g in games:
        if g.get('completed') is True and g.get('homePoints') is not None and g.get('awayPoints') is not None:
            fin[g['id']] = (g['homePoints'], g['awayPoints'])

    cmap = conf_map()
    closes = load_closes(state)
    from saif_policy import load_entries
    ent = load_entries(state)
    ent = {int(x['game_id']): x for x in ent.to_dict('records')} if len(ent) else {}
    rows = []
    for _, r in board.iterrows():
        gid = int(r['game_id'])
        if gid not in fin:
            continue
        hp, ap_ = fin[gid]
        actual = hp - ap_
        spread = r['market_spread']
        if spread is None or (isinstance(spread, float) and math.isnan(spread)):
            continue
        cover = actual + spread  # >0 means home covers
        close = closing_spread(closes, r['home_team'], r['away_team'], r['kickoff_utc']) if closes else None
        row = {
            'game_id': gid, 'away': r['away_team'], 'home': r['home_team'],
            'home_pts': hp, 'away_pts': ap_, 'actual_margin': actual,
            'home_conf': cmap.get(r['home_team']), 'away_conf': cmap.get(r['away_team']),
            'tier': matchup_tier(cmap.get(r['home_team']), cmap.get(r['away_team'])),
            'market_spread_home': spread, 'close_spread_home': close, 'home_cover_margin': round(cover, 1),
            'alpha_margin': r['independent_margin'], 'beta_margin': r['beta_margin'],
            'alpha_edge': round(r['independent_edge'], 2), 'beta_edge': round(r['beta_edge'], 2),
        }
        hf, af = r.get('qb_home_flag'), r.get('qb_away_flag')
        hf = hf if isinstance(hf, str) else ''
        af = af if isinstance(af, str) else ''
        row['qb_home_flag'], row['qb_away_flag'] = hf, af
        for tag, col in (('alpha', 'independent_edge'), ('beta', 'beta_edge')):
            pick, res, units = grade_side(r[col], cover)
            # muted = pick is on a team whose QB1 absence the models can't see (STALE)
            row[f'{tag}_qb_mute'] = bool((pick == 'home' and hf == 'STALE') or (pick == 'away' and af == 'STALE'))
            row[f'{tag}_pick'], row[f'{tag}_result'], row[f'{tag}_units'] = pick, res, units
            row[f'{tag}_bucket'] = bucket(r[col])
            row[f'{tag}_clv'] = clv_points(pick, spread, close)
        # SAIF (saif_policy.py). Three result sets, never mixed:
        #   saif_cons_*   consensus benchmark: every signal play at the consensus entry number, -110
        #   saif_*        paper tickets: observed executable quote (book/number/price) -- excluded when
        #                 there was no executable entry
        #   saif_placed_* bets actually placed (filled by hand in cfb_entries.csv)
        # QB news after entry never voids anything; it is flagged in saif_qb_news.
        en = ent.get(gid)
        keys = ('saif_locked_utc', 'saif_entry_spread_home', 'saif_edge', 'saif_qualifies', 'saif_skip_reason',
                'saif_play', 'saif_exec_status', 'saif_pick', 'saif_cons_result', 'saif_cons_units', 'saif_cons_clv',
                'saif_ticket_book', 'saif_ticket_point', 'saif_ticket_price', 'saif_ticket_raw_gap',
                'saif_result', 'saif_units', 'saif_clv', 'saif_move',
                'saif_placed_book', 'saif_placed_point', 'saif_placed_price', 'saif_placed_result', 'saif_placed_units',
                'saif_qb_news', 'saif_skip_result', 'entry_model_side', 'entry_move_model', 'entry_clv_model')
        row.update({k: None for k in keys})
        if en is not None:
            entry = float(en['entry_spread_home'])
            side = 'home' if float(en['raw_edge']) > 0 else 'away'
            truthy = lambda v: str(v).lower() == 'true'
            num = lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) or v == '' else float(v)
            play, qual = truthy(en['play']), truthy(en.get('qualifies', en['play']))
            row.update({'saif_locked_utc': en['locked_utc'], 'saif_entry_spread_home': entry,
                        'saif_edge': en['saif_edge'], 'saif_qualifies': qual, 'saif_play': play,
                        'saif_exec_status': en.get('exec_status') if isinstance(en.get('exec_status'), str) else '',
                        'saif_skip_reason': en.get('skip_reason') if isinstance(en.get('skip_reason'), str) else '',
                        # research, every locked game: did the line move toward the model's side after entry?
                        'entry_model_side': side, 'entry_move_model': clv_points(side, entry, spread),
                        'entry_clv_model': clv_points(side, entry, close)})
            margin_side = actual if side == 'home' else -actual
            side_num = lambda home_spread: home_spread if side == 'home' else -home_spread

            def settle(point, price):
                c = margin_side + point
                res = 'W' if c > 0 else 'L' if c < 0 else 'P'
                pay = price / 100 if price > 0 else 100 / -price
                return res, (pay if res == 'W' else -1.0 if res == 'L' else 0.0)

            if qual and not play:   # audit trail: what a skipped candidate would have done at consensus
                row['saif_skip_result'] = settle(side_num(entry), -110)[0]
            if play:
                row['saif_pick'] = side
                row['saif_cons_result'], row['saif_cons_units'] = settle(side_num(entry), -110)
                if close is not None:
                    row['saif_cons_clv'] = round(side_num(entry) - side_num(close), 2)
                tp, tpr = num(en.get('ticket_point')), num(en.get('ticket_price'))
                if tp is not None and tpr is not None:
                    row.update({'saif_ticket_book': en.get('ticket_book'), 'saif_ticket_point': tp,
                                'saif_ticket_price': tpr, 'saif_ticket_raw_gap': num(en.get('ticket_raw_gap'))})
                    row['saif_result'], row['saif_units'] = settle(tp, tpr)
                    if close is not None:
                        row['saif_clv'] = round(tp - side_num(close), 2)
                    row['saif_move'] = round(tp - side_num(spread), 2)
                pp, ppr = num(en.get('placed_point')), num(en.get('placed_price'))
                if pp is not None and ppr is not None:
                    row.update({'saif_placed_book': en.get('placed_book'), 'saif_placed_point': pp, 'saif_placed_price': ppr})
                    row['saif_placed_result'], row['saif_placed_units'] = settle(pp, ppr)
                flag_now = hf if side == 'home' else af
                flag_then = en.get(f'qb_{side}_flag_at_entry')
                row['saif_qb_news'] = bool(flag_now == 'STALE' and flag_then != 'STALE')
        row['alpha_err'] = abs(actual - r['independent_margin'])
        row['beta_err'] = abs(actual - r['beta_margin'])
        row['market_err'] = abs(actual - (-spread))
        rows.append(row)

    if not rows:
        raise SystemExit('No completed games matched yet -- try again after games finish.')
    df = pd.DataFrame(rows)
    out = state / 'graded'
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f'week{a.week}_graded.csv', index=False)

    print(f"\nWeek {a.week}: graded {len(df)} of {len(board)} board games (final scores in)")
    summ = []
    for tag, col in (('alpha', 'alpha_edge'), ('beta', 'beta_edge')):
        s = summarize(df, tag, col)
        s['mae'] = round(df[f'{tag}_err'].mean(), 2)
        s['week'] = a.week
        c = df[f'{tag}_clv'].dropna()
        s['clv_games'] = len(c)
        s['avg_clv'] = round(c.mean(), 2) if len(c) else None
        s['beat_close_pct'] = round((c > 0).mean() * 100, 1) if len(c) else None
        summ.append(s)
        print(f"  {tag.upper():5s} ATS {s['W']}-{s['L']}-{s['P']} ({s['ats_pct']}%)  "
              f"flat -110: {s['units_flat_110']:+.2f}u  ROI {s['roi_pct']}%  MAE {s['mae']}")
        if s['clv_games']:
            print(f"        CLV {s['avg_clv']:+.2f} pts avg, beat the close {s['beat_close_pct']}% "
                  f"({s['clv_games']} games with a closing snapshot)")
    for tag, label in (('saif_cons', 'SAIF consensus benchmark (-110, not executable)'),
                       ('saif', 'SAIF paper tickets (observed quotes)'), ('saif_placed', 'SAIF placed bets')):
        if f'{tag}_result' not in df or not df[f'{tag}_result'].isin(['W', 'L', 'P']).any():
            continue
        sp = df[df[f'{tag}_result'].isin(['W', 'L', 'P'])]
        s = summarize(df, tag, None)
        s['mae'] = None
        s['week'] = a.week
        clv_col = {'saif_cons': 'saif_cons_clv', 'saif': 'saif_clv'}.get(tag)
        c = sp[clv_col].dropna() if clv_col else pd.Series(dtype=float)
        s['clv_games'] = len(c)
        s['avg_clv'] = round(c.mean(), 2) if len(c) else None
        s['beat_close_pct'] = round((c > 0).mean() * 100, 1) if len(c) else None
        s['qb_news_after_entry'] = int(sp['saif_qb_news'].fillna(False).astype(bool).sum())
        summ.append(s)
        print(f"  {label}: {s['W']}-{s['L']}-{s['P']}  {s['units_flat_110']:+.2f}u"
              + (f"  CLV {s['avg_clv']:+.2f} pts ({s['beat_close_pct']}% beat close, n={s['clv_games']})" if s['clv_games'] else ''))
    if 'saif_exec_status' in df:
        ne = int((df['saif_exec_status'] == 'no executable entry').sum())
        if ne:
            print(f'  SAIF  {ne} signal play(s) had no executable quote: consensus benchmark only')
    sk = df[df['saif_skip_result'].notna()] if 'saif_skip_result' in df else df.iloc[0:0]
    if len(sk):
        print(f"  SAIF  skipped at entry (QB1 out): {len(sk)} -- would have gone "
              f"{(sk.saif_skip_result=='W').sum()}-{(sk.saif_skip_result=='L').sum()}-{(sk.saif_skip_result=='P').sum()}")
    mv = df['entry_move_model'].dropna() if 'entry_move_model' in df else []
    if len(mv):
        nz = mv[mv != 0]
        print(f"  Entry-line research ({len(mv)} locked games): line moved toward the model {f'{(nz > 0).mean():.0%} of {len(nz)} moves' if len(nz) else '(no moves)'}, "
              f"avg {mv.mean():+.2f} pts to the board line" + (f", {df['entry_clv_model'].dropna().mean():+.2f} to the close" if df['entry_clv_model'].notna().any() else ''))
    if 'alpha_qb_mute' in df:
        print('\n  QB1 flag check (STALE = pick on team missing QB1):')
        for tag in ('alpha', 'beta'):
            for lbl, m in (('muted', df[f'{tag}_qb_mute']), ('kept ', ~df[f'{tag}_qb_mute'])):
                g = df[m & df[f'{tag}_result'].isin(['W', 'L', 'P'])]
                if len(g):
                    print(f"    {tag:5s} {lbl}: {(g[f'{tag}_result']=='W').sum()}-{(g[f'{tag}_result']=='L').sum()}-{(g[f'{tag}_result']=='P').sum()}  {g[f'{tag}_units'].sum():+.2f}u")
    print(f"  MARKET MAE {round(df['market_err'].mean(), 2)} (pull-time line)")

    print('\n  ATS by edge size (Alpha / Beta):')
    for tag in ('alpha', 'beta'):
        t = df.groupby(f'{tag}_bucket')[f'{tag}_result'].agg(
            W=lambda x: (x == 'W').sum(), L=lambda x: (x == 'L').sum(), P=lambda x: (x == 'P').sum())
        for b in ['<2', '2-4', '4-7', '7+']:
            if b in t.index:
                print(f"    {tag:5s} {b:>4s}: {t.loc[b,'W']}-{t.loc[b,'L']}-{t.loc[b,'P']}")

    sf = out / 'summary.csv'
    new = pd.DataFrame(summ)
    new['market_mae'] = round(df['market_err'].mean(), 2)
    if sf.exists():
        old = pd.read_csv(sf)
        old = old[old['week'] != a.week]
        new = pd.concat([old, new], ignore_index=True)
    new.to_csv(sf, index=False)
    print(f"\nSaved {out / f'week{a.week}_graded.csv'} and {sf}")
    n_close = int(df['close_spread_home'].notna().sum())
    print(f'Note: W/L graded against the board line at last pull; CLV vs closing snapshot for {n_close} of {len(df)} games.')


if __name__ == '__main__':
    main()
