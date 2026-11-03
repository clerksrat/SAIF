"""Render docs/cbb.html: the CBB dry-run board, styled like the football board.

Reuses the football template's stylesheet (assets/page_template.html) and logo so both pages
look like one site; adds the go-wet scorecard and basketball-specific filters.
"""
import html
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent.parent
e = html.escape
GATE_N, WIN = 300, 100 / 110
STRONG_SIDE, STRONG_TOTAL = 5.0, 6.0      # solid pill above these; outline between the play threshold and these


# ------------------------------------------------------------------ shared site pieces
def football_css():
    t = (ROOT / 'assets' / 'page_template.html').read_text(encoding='utf-8')
    return re.search(r'<style>(.*?)</style>', t, re.S).group(1)


def logo():
    return (ROOT / 'assets' / 'logo_tag.txt').read_text(encoding='utf-8').strip()


def nav():
    for line in (ROOT / 'assets' / 'tabs.txt').read_text().splitlines():
        h, html_ = line.split('\t', 1)
        if h == 'cbb.html':
            return html_
    return ''


# ------------------------------------------------------------------ formatting
def sp(x):
    return 'PK' if x == 0 else f'{x:+g}'


def side_pick(home, away, edge, spread):
    return f'{home} {sp(spread)}' if edge > 0 else f'{away} {sp(-spread)}'


def stats(df, res, clv):
    if df is None or not len(df):
        return None
    d = df[df[res].notna()]
    if not len(d):
        return None
    w, l, p = int((d[res] > 0).sum()), int((d[res] < 0).sum()), int((d[res] == 0).sum())
    c = d[clv].dropna()
    return {'n': len(d), 'w': w, 'l': l, 'p': p, 'pct': w / (w + l) if w + l else math.nan,
            'units': w * WIN - l, 'clv': c.mean() if len(c) else math.nan,
            'beat': (c > 0).mean() if len(c) else math.nan, 'worse': (c < 0).mean() if len(c) else math.nan}


# ------------------------------------------------------------------ scorecard
def scorecard(title, s, threshold):
    if not s:
        body = ('<p class="sc-empty">No graded plays yet. Results land the morning after each slate.</p>')
        return (f'<div class="sc"><div class="sc-head"><h3>{title}</h3><span class="sc-th">edge {threshold:g}+</span>'
                f'<span class="chip">Collecting</span></div>{body}</div>')
    passing = s['n'] >= GATE_N and s['clv'] > 0 and s['beat'] > s['worse']
    pct = min(s['n'] / GATE_N, 1) * 100
    clv_cls = 'pos' if s['clv'] > 0 else 'neg' if s['clv'] < 0 else ''
    beat_ok = s['beat'] > s['worse']
    chip = '<span class="chip ok">Gates met</span>' if passing else '<span class="chip">Not yet</span>'
    return f'''<div class="sc"><div class="sc-head"><h3>{title}</h3><span class="sc-th">edge {threshold:g}+</span>{chip}</div>
<div class="sc-bar" role="img" aria-label="{s['n']} of {GATE_N} graded plays"><span style="width:{pct:.0f}%"></span></div>
<p class="sc-n"><b>{s['n']}</b> / {GATE_N} graded plays</p>
<div class="sc-stats">
<div><span class="lbl">Avg CLV</span><b class="{clv_cls}">{s['clv']:+.2f}</b><small>target &gt; 0</small></div>
<div><span class="lbl">Beat close</span><b class="{'pos' if beat_ok else 'neg'}">{s['beat']*100:.0f}%</b><small>worse {s['worse']*100:.0f}%</small></div>
<div><span class="lbl">At entry</span><b>{s['w']}-{s['l']}-{s['p']}</b><small>{s['units']:+.1f}u</small></div>
</div></div>'''


def bucket_table(g):
    if g is None or not len(g):
        return ''
    rows = []
    for kind, ecol, res, clv, cuts in (('Side', 'side_edge', 'side_result', 'side_clv', (0, 1.5, 3, 5, 99)),
                                       ('Total', 'total_edge', 'total_result', 'total_clv', (0, 2, 4, 6, 99))):
        for lo, hi in zip(cuts, cuts[1:]):
            s = stats(g[(g[ecol].abs() >= lo) & (g[ecol].abs() < hi)], res, clv)
            if s:
                lab = f'{lo:g}&ndash;{hi:g}' if hi < 99 else f'{lo:g}+'
                rows.append(f"<tr><td>{kind} {lab}</td><td>{s['n']}</td><td>{s['w']}-{s['l']}-{s['p']}</td>"
                            f"<td>{s['clv']:+.2f}</td><td>{s['beat']*100:.0f}%</td></tr>")
    return ('<div class="tablewrap"><table><tr><th>Edge</th><th>Games</th><th>At entry</th><th>Avg CLV</th>'
            '<th>Beat close</th></tr>' + ''.join(rows) + '</table></div>')


def recent(g, side_play, total_play):
    if g is None or not len(g):
        return ''
    rows = []
    for r in g.sort_values('tip_utc', ascending=False).itertuples():
        for kind, edge, play, res, clv, txt, close in (
                ('Side', r.side_edge, side_play, r.side_result, r.side_clv,
                 side_pick(r.home, r.away, r.side_edge, r.entry_spread),
                 None if pd.isna(r.close_spread) else (r.close_spread if r.side_edge > 0 else -r.close_spread)),
                ('Total', r.total_edge, total_play, r.total_result, r.total_clv,
                 f"{'Over' if r.total_edge > 0 else 'Under'} {r.entry_total:g}",
                 None if pd.isna(r.close_total) else r.close_total)):
            if pd.isna(edge) or abs(edge) < play:
                continue
            tag = {1: '<span class="res res-W">W</span>', -1: '<span class="res res-L">L</span>',
                   0: '<span class="res res-P">P</span>'}.get(res, '')
            cl = '' if close is None else (sp(close) if kind == 'Side' else f'{close:g}')
            cv = '' if pd.isna(clv) else f'<span class="{"pos" if clv > 0 else "neg" if clv < 0 else ""}">{clv:+.1f}</span>'
            rows.append(f'<tr><td>{e(str(r.date))[5:]}</td><td>{kind}</td><td>{e(txt)}</td><td>{cl}</td><td>{cv}</td><td>{tag}</td></tr>')
        if len(rows) >= 30:
            break
    if not rows:
        return ''
    return ('<p class="contrib-sub">Recent plays</p><div class="tablewrap"><table><tr><th>Date</th><th></th><th>Pick (entry)</th>'
            '<th>Close</th><th>CLV</th><th></th></tr>' + ''.join(rows) + '</table></div>')


# ------------------------------------------------------------------ game cards
def pill(text, edge, play, strong):
    if abs(edge) < play:
        return '<span class="noplay">No play</span>'
    return f'<span class="pick {"edge-strong" if abs(edge) >= strong else "edge-mid"}">{e(text)}</span>'


def card(r, i, now, side_play, total_play):
    t = r.tip.tz_convert(ET)
    done = r.status == 'final'
    tipped = r.tip <= now and not done
    neutral = r['loc'] == 0
    has_side = not pd.isna(r.entry_spread)
    has_total = not pd.isna(r.entry_total)
    se = r.model_margin + r.entry_spread if has_side else 0.0
    te = r.model_total - r.entry_total if has_total else 0.0
    confs = [c for c in (r.awayConference, r.homeConference) if isinstance(c, str)]
    conf_txt = ' / '.join(dict.fromkeys(confs))
    meta = [f'<span>{t:%-I:%M %p} ET</span>']
    if conf_txt:
        meta.append(f'<span class="tiertag">{e(conf_txt)}</span>')
    if neutral:
        meta.append('<span class="finaltag">Neutral</span>')
    if tipped:
        meta.append('<span class="finaltag livetag">Tipped</span>')
    model_line = round(-r.model_margin * 2) / 2
    side_tile = (f'<div class="mtile"><div class="mlabel">Side</div>'
                 f'{pill(side_pick(r.home, r.away, se, r.entry_spread), se, side_play, STRONG_SIDE)}'
                 f'<div class="msub">Model <b>{e(r.home)} {sp(model_line)}</b> <span class="dot">&middot;</span> '
                 f'<span class="edge">Edge <b>{abs(se):.1f}</b></span></div></div>'
                 if has_side else '<div class="mtile"><div class="mlabel">Side</div><span class="noplay">No line</span></div>')
    total_tile = (f'<div class="mtile"><div class="mlabel">Total</div>'
                  f'{pill(("Over " if te > 0 else "Under ") + f"{r.entry_total:g}", te, total_play, STRONG_TOTAL)}'
                  f'<div class="msub">Model <b>{r.model_total:.1f}</b> <span class="dot">&middot;</span> '
                  f'<span class="edge">Edge <b>{abs(te):.1f}</b></span></div></div>'
                  if has_total else '<div class="mtile"><div class="mlabel">Total</div><span class="noplay">No line</span></div>')
    books = ''
    m = re.search(r'\((\d+) books\)', str(r.entry_src or ''))
    src = f'{m.group(1)} books' if m else ('CBBD line' if r.entry_src == 'CBBD' else '')
    line = (f'<p class="line"><span class="lbl">Line</span><b>{e(r.home)} {sp(r.entry_spread)}</b>'
            + (f' &middot; <span class="lbl">Total</span><b>{r.entry_total:g}</b>' if has_total else '')
            + (f' <span class="movetag">&middot; {src}</span>' if src else '') + '</p>') if has_side else \
        '<p class="line"><span class="lbl">Line</span><b>not posted</b></p>'
    data = {
        'time': int(r.tip.timestamp()), 'hour': t.hour + t.minute / 60, 'done': int(done),
        'search': f'{r.away} {r.home}'.lower(), 'conf': '|'.join(confs),
        'se': round(abs(se), 2) if has_side else 0, 'te': round(abs(te), 2) if has_total else 0,
        'splay': int(has_side and abs(se) >= side_play), 'tplay': int(has_total and abs(te) >= total_play),
        'gid': int(r.game_id), 'home': r.home, 'away': r.away}
    if data['splay']:      # pick side and the number taken, from the picked team's side
        data['sside'], data['sline'] = ('home', r.entry_spread) if se > 0 else ('away', -r.entry_spread)
    if data['tplay']:
        data['tside'], data['tline'] = ('over' if te > 0 else 'under'), r.entry_total
    attrs = ' '.join(f'data-{k}="{e(str(v))}"' for k, v in data.items())
    return (f'<article class="game{" done" if done else ""}" id="g{i}" {attrs}><div class="meta">{"".join(meta)}</div>'
            f'<h2>{e(r.away)} <small>{"vs" if neutral else "at"}</small> {e(r.home)}</h2>{line}'
            f'<div class="models">{side_tile.replace("class=\"mtile\"", "class=\"mtile\" data-k=\"side\"", 1)}'
            f'{total_tile.replace("class=\"mtile\"", "class=\"mtile\" data-k=\"total\"", 1)}</div></article>')


def plays_list(board, now, side_play, total_play):
    items = []
    for i, r in enumerate(board.itertuples()):
        if r.tip <= now:
            continue
        t = r.tip.tz_convert(ET)
        if not pd.isna(r.entry_spread):
            se = r.model_margin + r.entry_spread
            if abs(se) >= side_play:
                items.append((r.tip, i, side_pick(r.home, r.away, se, r.entry_spread), 'Side', abs(se), t, r))
        if not pd.isna(r.entry_total):
            te = r.model_total - r.entry_total
            if abs(te) >= total_play:
                items.append((r.tip, i, f"{'Over' if te > 0 else 'Under'} {r.entry_total:g}", 'Total', abs(te), t, r))
    items.sort(key=lambda x: (x[0], x[3]))
    lis = ''.join(
        f'<li><button type="button" class="play" data-go="g{i}" data-kind="{kind.lower()}">'
        f'<span class="bet">{e(txt)}</span><span class="when">{t:%-I:%M %p}</span>'
        f'<span class="sub">{kind} &middot; edge {edge:.1f} &middot; {e(r.away)} {"vs" if r.loc == 0 else "at"} {e(r.home)}</span>'
        f'</button></li>' for _, i, txt, kind, edge, t, r in items)
    return items, lis


# ------------------------------------------------------------------ page
LIVE_JS = r'''// ---------- live + final scores: /api/cbb-scores (Netlify function, cached 10 min) ----------
const DATE=$('cards').dataset.date;
function grade(c,g){const d=c.dataset,margin=g.hp-g.ap,total=g.hp+g.ap,out={};
 if(d.sside){const cov=(d.sside==='home'?margin:-margin)+Number(d.sline);out.side=cov>0?'W':cov<0?'L':'P'}
 if(d.tside){const diff=total-Number(d.tline),v=d.tside==='over'?diff:-diff;out.total=v>0?'W':v<0?'L':'P'}
 return out}
function badge(r){const b=document.createElement('span');b.className='res res-'+r;b.textContent={W:'Won',L:'Lost',P:'Push'}[r];return b}
function applyScores(data){const by={};(data.games||[]).forEach(g=>by[g.id]=g);let changed=false;
 cards.forEach(c=>{const d=c.dataset,g=by[d.gid];if(!g||d.graded==='1'||g.hp==null)return;
  const meta=c.querySelector('.meta');let tag=meta.querySelector('.livetag,.scoretag');
  if(!tag){tag=document.createElement('span');meta.appendChild(tag)}
  if(g.status!=='final'){tag.className='finaltag livetag';tag.textContent=`Live: ${d.away} ${g.ap}, ${d.home} ${g.hp}`;return}
  tag.className='finaltag scoretag';tag.textContent=`Final: ${d.away} ${g.ap}, ${d.home} ${g.hp}`;
  d.graded='1';d.done='1';c.classList.add('done');changed=true;const res=grade(c,g);
  ['side','total'].forEach(k=>{if(!res[k])return;const p=c.querySelector(`.mtile[data-k=${k}] .pick`);if(p)p.after(badge(res[k]));
   document.querySelectorAll(`.play[data-go="${c.id}"][data-kind="${k}"]`).forEach(b=>{const s=document.createElement('span');s.className='play-res';s.append(badge(res[k]));b.append(s)})})});
 if(changed)render()}
async function pollScores(){try{const r=await fetch('/api/cbb-scores?date='+DATE);if(r.ok)applyScores(await r.json())}catch(e){}}
const pending=()=>{const now=Date.now()/1000;return cards.some(c=>c.dataset.done!=='1'&&now>Number(c.dataset.time))};
if(DATE&&/^https?:/.test(location.protocol)){pollScores();
 setInterval(()=>{if(!document.hidden&&pending())pollScores()},5*60*1000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&pending())pollScores()})}
'''

EXTRA_CSS = '''
.sc-wrap{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:18px}
.sc{background:var(--paper-raised);border:1px solid var(--rule);border-radius:14px;padding:14px 16px;min-width:0}
.sc-head{display:flex;align-items:baseline;gap:8px}
.sc h3{font-family:'Fraunces',serif;font-weight:600;font-size:19px;margin:0;color:var(--ink)}
.sc-th{font-size:12px;color:var(--ink-faint);flex:1}
.chip{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:999px;background:var(--rule);color:var(--ink-soft)}
.chip.ok{background:#1F3A27;color:var(--win)}
.sc-bar{height:6px;background:var(--rule);border-radius:3px;margin:12px 0 6px;overflow:hidden}
.sc-bar span{display:block;height:100%;background:var(--accent);border-radius:3px}
.sc-n{font-size:12.5px;color:var(--ink-faint);margin:0 0 10px}.sc-n b{color:var(--ink)}
.sc-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.sc-stats div{background:var(--paper);border:1px solid var(--rule);border-radius:10px;padding:8px 10px;min-width:0}
.sc-stats .lbl{display:block;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-faint);font-weight:600}
.sc-stats b{display:block;font:500 17px 'IBM Plex Mono',monospace;color:var(--ink);margin:3px 0 1px}
.sc-stats b.pos{color:var(--win)}.sc-stats b.neg{color:var(--loss)}
.sc-stats small{font-size:11px;color:var(--ink-faint)}
.sc-empty{font-size:13px;color:var(--ink-faint);margin:10px 0 0}
.plays-tabs{display:flex;gap:6px;margin:0 0 10px}
.plays-tabs button{width:auto;min-height:34px;padding:6px 12px;font-size:12.5px;border-radius:999px}
.plays-tabs button.on{background:var(--accent);color:#14261D;border-color:var(--accent)}
.filters.cbb{grid-template-columns:2fr 1fr 1fr 1fr 1fr auto}
.livetag{background:#3A2321;color:var(--loss)}.play .res{margin-left:0}
.play-res{grid-column:2;text-align:right}
@media(max-width:900px){.sc-wrap{grid-template-columns:1fr}.filters.cbb{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.sc-stats b{font-size:15px}.sc{padding:12px}}
'''


def render(board, graded, entries, today, now, side_play, total_play):
    g = graded if graded is not None and len(graded) else None
    s_side = stats(g[g.side_edge.abs() >= side_play], 'side_result', 'side_clv') if g is not None else None
    s_tot = stats(g[g.total_edge.abs() >= total_play], 'total_result', 'total_clv') if g is not None else None
    board = board.sort_values('tip').reset_index(drop=True) if len(board) else board
    cards = ''.join(card(r, i, now, side_play, total_play) for i, r in board.iterrows())
    items, lis = plays_list(board, now, side_play, total_play) if len(board) else ([], '')
    n_side = sum(1 for x in items if x[3] == 'Side')
    n_tot = len(items) - n_side
    confs = sorted({c for col in ('homeConference', 'awayConference') if col in board for c in board[col].dropna()})
    conf_opts = ''.join(f'<option>{e(c)}</option>' for c in confs)
    n = len(board)
    updated = f'{now.astimezone(ET):%-I:%M %p} ET'
    plays_html = (f'''<section class="plays" id="plays" aria-labelledby="playsTitle">
<div class="plays-head"><h3 id="playsTitle">Today&rsquo;s plays</h3><span class="plays-count">{n_side} side &middot; {n_tot} total &middot; paper only</span></div>
<p class="plays-note">Side plays need a model edge of {side_play:g}+ points vs this morning&rsquo;s line; totals need {total_play:g}+. Logged for grading, not bet. Tap a play to jump to its game.</p>
<div class="plays-tabs" role="group" aria-label="Play type"><button type="button" class="on" data-k="">All</button><button type="button" data-k="side">Sides</button><button type="button" data-k="total">Totals</button></div>
<ol class="plays-list" id="playsList">{lis}</ol>
<button type="button" class="plays-more" id="playsMore" hidden></button>
</section>''' if items else '')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#12241C"><link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/icons/apple-touch-icon.png"><link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="SAIF"><meta name="apple-mobile-web-app-status-bar-style" content="black"><script>if('serviceWorker' in navigator){{addEventListener('load',function(){{navigator.serviceWorker.register('/sw.js').catch(function(){{}})}})}}</script><title>SAIF · College Basketball</title><style>{football_css()}{EXTRA_CSS}</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"><main>
{nav()}
<header class="top">
  {logo()}
  <div>
    <p class="kicker">SAIF &middot; College Basketball &middot; Dry run</p>
    <h1>Paper first. Capital later.</h1>
    <p class="sub">{today:%A, %B %-d} &middot; {n} games &middot; updated {updated}</p>
  </div>
</header>

<div class="warn"><b>No SAIF capital until the gates are met.</b> Every game is logged at this morning&rsquo;s line and graded the next day against its closing line. The test is whether the line moves our way (CLV), not the win&ndash;loss record.</div>

<div class="sc-wrap">{scorecard('Sides', s_side, side_play)}{scorecard('Totals', s_tot, total_play)}</div>
<details class="about"><summary>Gates, results by edge &amp; recent plays</summary>
<p><b>Go-wet gates</b> (sides and totals separately): {GATE_N} graded plays, average CLV above zero, and the line moving our way more often than against us. CLV = points the line moved toward our side between this morning and tip.</p>
{bucket_table(g)}
{recent(g, side_play, total_play)}
<p><b>Model</b> &mdash; opponent-adjusted offensive and defensive efficiency plus tempo, refit every morning from this season&rsquo;s games with last season as a fading prior. Totals use a separately tuned version that discounts hot and cold three-point shooting. Backtest (2022&ndash;26): neither version beats closing lines, but against opening lines the market moved toward the model, more so as the edge grew. Research tool, not betting advice.</p>
</details>

{plays_html}

<p class="legend"><b>Line</b> = this morning&rsquo;s consensus home spread, favorite shown with &minus;. <b>Pick</b> solid = side edge {STRONG_SIDE:g}+ / total edge {STRONG_TOTAL:g}+; outline = play ({side_play:g}+ side, {total_play:g}+ total). Smaller edges show as <b>No play</b>.</p>

<div class="filters cbb" id="filters">
<div class="f-search"><label for="search">Team search</label><input id="search" placeholder="Duke, Gonzaga&hellip;" type="search" autocomplete="off"></div>
<div class="f-plays"><label for="show">Show</label><select id="show"><option value="all">All games</option><option value="any">Any play</option><option value="side">Side plays</option><option value="total">Total plays</option></select></div>
<div class="f-sort"><label for="sort">Sort</label><select id="sort"><option value="time">Tip time</option><option value="se">Largest side edge</option><option value="te">Largest total edge</option></select></div>
<div class="f-more"><label for="conf">Conference</label><select id="conf"><option value="">All conferences</option>{conf_opts}</select></div>
<div class="f-more"><label for="win">Tip time &middot; ET</label><select id="win"><option value="">Any time</option><option value="0-17">Before 5 PM</option><option value="17-20">5&ndash;8 PM</option><option value="20-30">8 PM or later</option></select></div>
<div class="f-more"><label>&nbsp;</label><button id="reset" type="button">Reset</button></div>
<button class="f-toggle" id="ftoggle" type="button" aria-expanded="false">More filters</button>
</div>

<p id="count" role="status" aria-live="polite">{n} of {n} games shown</p>
<div id="cards" class="grid" data-date="{today.isoformat()}">{cards}</div>
<p id="empty" hidden>No matching games. Change the filters or reset.</p>
</main><script>
const $=id=>document.getElementById(id),cards=Array.from(document.querySelectorAll('article.game'));
function render(){{const q=$('search').value.trim().toLowerCase(),show=$('show').value,sort=$('sort').value,conf=$('conf').value,win=$('win').value;let n=0;
const [lo,hi]=win?win.split('-').map(Number):[0,99];
cards.sort((a,b)=>Number(a.dataset.done)-Number(b.dataset.done)||(sort==='time'?Number(a.dataset.time)-Number(b.dataset.time):Number(b.dataset[sort])-Number(a.dataset[sort])||Number(a.dataset.time)-Number(b.dataset.time)));
cards.forEach(c=>{{const d=c.dataset,h=Number(d.hour);const ok=d.search.includes(q)&&(!conf||d.conf.split('|').includes(conf))&&h>=lo&&h<hi&&(show==='all'||(show==='side'&&d.splay==='1')||(show==='total'&&d.tplay==='1')||(show==='any'&&(d.splay==='1'||d.tplay==='1')));c.hidden=!ok;if(ok)n++;$('cards').append(c)}});
$('count').textContent=n+' of '+cards.length+' games shown';$('empty').hidden=n>0}}
const defaults={{search:'',show:'all',sort:'time',conf:'',win:''}};
Object.keys(defaults).forEach(id=>$(id).addEventListener(id==='search'?'input':'change',render));
$('reset').addEventListener('click',()=>{{Object.entries(defaults).forEach(([id,v])=>$(id).value=v);render()}});
$('ftoggle').addEventListener('click',ev=>{{const f=$('filters'),on=f.classList.toggle('expanded');ev.target.setAttribute('aria-expanded',on);ev.target.textContent=on?'Fewer filters':'More filters'}});
render();
// plays box: type tabs, show 6 then "show all", tap to jump
const list=$('playsList');if(list){{const items=Array.from(list.children),more=$('playsMore');let kind='',all=false;
function draw(){{const vis=items.filter(li=>!kind||li.firstChild.dataset.kind===kind);items.forEach(li=>li.hidden=true);vis.forEach((li,i)=>li.hidden=!all&&i>=6);
more.hidden=vis.length<=6;more.textContent=all?'Show fewer':'Show all '+vis.length+' plays'}}
document.querySelectorAll('.plays-tabs button').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('.plays-tabs button').forEach(x=>x.classList.toggle('on',x===b));kind=b.dataset.k;all=false;draw()}}));
more.addEventListener('click',()=>{{all=!all;draw()}});
list.addEventListener('click',ev=>{{const b=ev.target.closest('.play');if(!b)return;const c=$(b.dataset.go);if(c.hidden){{Object.entries(defaults).forEach(([id,v])=>$(id).value=v);render()}}c.scrollIntoView({{behavior:'smooth',block:'center'}});c.classList.remove('flash');void c.offsetWidth;c.classList.add('flash')}});draw()}}
{LIVE_JS}
</script></html>'''
