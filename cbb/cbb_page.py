"""Render docs/cbb.html: today's CBB dry-run board + the scorecard against the go-wet gates."""
import html
import math
from pathlib import Path

import numpy as np
import pandas as pd

from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

e = html.escape
ROOT = Path(__file__).resolve().parent.parent
GATE_N, WIN = 300, 100 / 110


def sp(x):
    return 'PK' if x == 0 else f'{x:+g}'


def pick_text(home, away, edge, spread):
    return f'{e(home)} {sp(spread)}' if edge > 0 else f'{e(away)} {sp(-spread)}'


def stats(df, res, clv):
    d = df[df[res].notna() & df[clv].notna()] if len(df) else df
    if not len(d):
        return None
    w, l, p = int((d[res] > 0).sum()), int((d[res] < 0).sum()), int((d[res] == 0).sum())
    return {'n': len(d), 'w': w, 'l': l, 'p': p, 'pct': w / (w + l) if w + l else math.nan,
            'units': w * WIN - l, 'clv': d[clv].mean(), 'beat': (d[clv] > 0).mean(), 'worse': (d[clv] < 0).mean()}


def gate_rows(s):
    if not s:
        return '<p class="muted">No graded plays yet &mdash; the first results land the morning after the first slate.</p>'
    checks = [
        ('Graded plays', f"{s['n']} / {GATE_N}", s['n'] >= GATE_N),
        ('Average CLV', f"{s['clv']:+.2f} pts", s['clv'] > 0),
        ('Beat the close', f"{s['beat']*100:.0f}% (worse {s['worse']*100:.0f}%)", s['beat'] > s['worse']),
        ('Record at entry', f"{s['w']}-{s['l']}-{s['p']} &middot; {s['pct']*100:.1f}% &middot; {s['units']:+.1f}u", None),
    ]
    out = []
    for label, val, ok in checks:
        mark = '' if ok is None else ('<span class="ok">&#10003;</span>' if ok else '<span class="no">&#9675;</span>')
        out.append(f'<div class="gate"><span>{label}</span><b>{val}</b>{mark}</div>')
    return ''.join(out)


def bucket_table(g):
    if g is None or not len(g):
        return ''
    rows = []
    for lo, hi in ((0, 1.5), (1.5, 3), (3, 5), (5, 99)):
        d = g[(g.side_edge.abs() >= lo) & (g.side_edge.abs() < hi)]
        s = stats(d, 'side_result', 'side_clv')
        if s:
            rows.append(f"<tr><td>{f'{lo:g}&ndash;{hi:g}' if hi < 99 else f'{lo:g}+'}</td><td>{s['n']}</td>"
                        f"<td>{s['w']}-{s['l']}-{s['p']}</td><td>{s['clv']:+.2f}</td><td>{s['beat']*100:.0f}%</td></tr>")
    return ('<table><tr><th>Side edge</th><th>Games</th><th>At entry</th><th>Avg CLV</th><th>Beat close</th></tr>'
            + ''.join(rows) + '</table>')


def card(r, side_play, total_play):
    t = r.tip.tz_convert('America/New_York')
    at = 'vs' if r['loc'] == 0 else '@'
    has_line = not pd.isna(r.entry_spread)
    se = r.model_margin + r.entry_spread if has_line else np.nan
    te = r.model_total - r.entry_total if not pd.isna(r.entry_total) else np.nan
    play = has_line and abs(se) >= side_play
    tplay = not pd.isna(te) and abs(te) >= total_play
    model_line = -r.model_margin
    cell = lambda k, v, hot=False: f'<div><span class="k">{k}</span><b class="{"hot" if hot else ""}">{v}</b></div>'
    side = (f'<div class="row">{cell("Line", e(r.home) + " " + sp(r.entry_spread))}'
            f'{cell("Model", e(r.home) + " " + sp(round(model_line * 2) / 2))}{cell("Edge", f"{abs(se):.1f}", play)}</div>'
            if has_line else '<div class="row muted">No line yet</div>')
    total = (f'<div class="row">{cell("Total", f"{r.entry_total:g}")}{cell("Model", f"{r.model_total:.1f}")}'
             f'{cell("Edge", ("O " if te > 0 else "U ") + f"{abs(te):.1f}", tplay)}</div>'
             if not pd.isna(te) else '')
    tags = ''
    if play:
        tags += f'<span class="tag">Side &middot; {pick_text(r.home, r.away, se, r.entry_spread)}</span>'
    if tplay:
        tags += f'<span class="tag">Total &middot; {"Over" if te > 0 else "Under"} {r.entry_total:g}</span>'
    return (f'<div class="card{" play" if play else ""}"><div class="when">{t:%-I:%M %p}'
            f'<span class="src">{e(r.entry_src or "")}</span></div>'
            f'<div class="teams">{e(r.away)} <span class="at">{at}</span> {e(r.home)}</div>{side}{total}'
            f'{"<div>" + tags + "</div>" if tags else ""}</div>')


def recent(g, side_play):
    if g is None or not len(g):
        return ''
    g = g[g.side_edge.abs() >= side_play].sort_values('tip_utc', ascending=False).head(15)
    rows = []
    for r in g.itertuples():
        res = {1: '<span class="w">W</span>', -1: '<span class="l">L</span>', 0: 'P'}.get(r.side_result, '')
        clv = '' if pd.isna(r.side_clv) else f'{r.side_clv:+.1f}'
        rows.append(f'<tr><td>{e(r.date)}</td><td>{pick_text(r.home, r.away, r.side_edge, r.entry_spread)}</td>'
                    f'<td>{"" if pd.isna(r.close_spread) else sp(r.close_spread if r.side_edge > 0 else -r.close_spread)}</td>'
                    f'<td>{clv}</td><td>{res}</td></tr>')
    return ('<h2>Recent plays</h2><table><tr><th>Date</th><th>Pick (entry)</th><th>Close</th><th>CLV</th><th></th></tr>'
            + ''.join(rows) + '</table>')


def nav():
    for line in (ROOT / 'assets' / 'tabs.txt').read_text().splitlines():
        h, html_ = line.split('\t', 1)
        if h == 'cbb.html':
            return html_
    return ''


def render(board, graded, entries, today, now, side_play, total_play):
    NAV = nav()
    g = graded if graded is not None and len(graded) else None
    plays = g[g.side_edge.abs() >= side_play] if g is not None else None
    s_play = stats(plays, 'side_result', 'side_clv') if plays is not None else None
    s_all = stats(g, 'side_result', 'side_clv') if g is not None else None
    t_play = stats(g[g.total_edge.abs() >= total_play], 'total_result', 'total_clv') if g is not None else None
    n_tplays = int(((board.model_total - board.entry_total).abs() >= total_play).sum()) if len(board) else 0
    board = board.sort_values('tip') if len(board) else board
    cards = ''.join(card(r, side_play, total_play) for _, r in board.iterrows()) or \
        '<p class="muted">No D1 games on the board today.</p>'
    n_plays = int(((board.model_margin + board.entry_spread).abs() >= side_play).sum()) if len(board) else 0
    line = lambda s, lbl: (f'<p class="sub2">{lbl}: {s["n"]} graded &middot; {s["w"]}-{s["l"]}-{s["p"]} '
                           f'&middot; CLV {s["clv"]:+.2f} &middot; beat close {s["beat"]*100:.0f}%</p>' if s else '')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#12241C">
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<title>SAIF · College Basketball</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--paper:#12241C;--raised:#1A2E24;--ink:#F7F3E7;--soft:#CBD6CD;--faint:#8FA095;--rule:#2C3F35;--accent:#D4B45C;--accent-soft:#2A2413;--win:#6FBF7B;--loss:#E07A70}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 'IBM Plex Sans',system-ui,-apple-system,sans-serif}}
main{{max-width:760px;margin:0 auto;padding:20px 16px 48px}}
h1{{font:600 28px/1.15 Fraunces,serif;margin:0}}h2{{font:600 19px Fraunces,serif;margin:28px 0 10px}}
.sub{{color:var(--soft);margin:6px 0 0}}.sub a{{color:var(--accent)}}.sub2{{color:var(--faint);font-size:13px;margin:6px 0}}
.banner{{background:var(--accent-soft);border:1px solid #4a3f1c;color:var(--accent);border-radius:8px;padding:10px 12px;margin:16px 0;font-size:14px}}
.gates{{display:grid;gap:6px}}.gate{{display:flex;gap:10px;align-items:baseline;background:var(--raised);border:1px solid var(--rule);border-radius:8px;padding:9px 12px}}
.gate span:first-child{{color:var(--soft);flex:1}}.gate b{{font:500 14px 'IBM Plex Mono',ui-monospace,monospace}}.ok{{color:var(--win)}}.no{{color:var(--faint)}}
.muted{{color:var(--faint)}}
.card{{background:var(--raised);border:1px solid var(--rule);border-radius:10px;padding:10px 12px;margin:8px 0}}
.card.play{{border-color:var(--accent)}}.when{{color:var(--faint);font-size:12px;display:flex;justify-content:space-between}}
.teams{{font-weight:600;margin:2px 0 6px}}.at{{color:var(--faint);font-weight:400}}
.row{{display:grid;grid-template-columns:1.6fr 1.6fr .8fr;gap:8px;margin-top:6px}}.row>div{{min-width:0}}
.k{{display:block;color:var(--faint);font:11px 'IBM Plex Sans',system-ui,sans-serif;text-transform:uppercase;letter-spacing:.04em}}
.row b{{display:block;font:500 13px 'IBM Plex Mono',ui-monospace,monospace;color:var(--soft);overflow-wrap:anywhere}}.row b.hot{{color:var(--accent)}}
.hot{{color:var(--accent)}}.tag{{display:inline-block;margin:8px 6px 0 0;background:var(--accent-soft);color:var(--accent);border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:6px 4px;border-bottom:1px solid var(--rule)}}th{{color:var(--faint);font-weight:500}}
td{{font-family:'IBM Plex Mono',monospace}}.w{{color:var(--win);font-weight:600}}.l{{color:var(--loss);font-weight:600}}
footer{{color:var(--faint);font-size:12px;margin-top:28px}}
</style><main>
{NAV}
<h1>College Basketball</h1>
<p class="sub">Board for {today:%a %b %-d} &middot; updated {now.astimezone(ET):%-I:%M %p ET}</p>
<div class="banner"><b>Dry run.</b> Paper only &mdash; no SAIF capital until the gates below are met. Entry line = this morning&rsquo;s consensus; every game is graded against its closing line.</div>
<h2>Go-wet gates &middot; sides <span class="muted" style="font:400 13px 'IBM Plex Sans'">edge &ge; {side_play:g}</span></h2>
<div class="gates">{gate_rows(s_play)}</div>
{line(s_all, 'All games (any edge)')}
{bucket_table(g)}
<h2>Go-wet gates &middot; totals <span class="muted" style="font:400 13px 'IBM Plex Sans'">edge &ge; {total_play:g}</span></h2>
<div class="gates">{gate_rows(t_play)}</div>
<h2>Today &middot; {len(board)} games &middot; {n_plays} side plays &middot; {n_tplays} total plays</h2>
{cards}
{recent(g, side_play)}
<footer>Model: opponent-adjusted efficiency + tempo, refit daily from this season&rsquo;s games with last season as a fading prior.
Edge = model margin vs the entry line, in points. CLV = points the line moved toward our side between entry and close.
Totals use a separately tuned version that discounts hot and cold three-point shooting. Research tool, not betting advice.</footer>
</main></html>'''
