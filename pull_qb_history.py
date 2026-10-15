"""Pull per-game QB passing lines (who threw) for 2023-2025 plus season QB PPA, for the QB-out backtest.
About 48 CFBD calls (you have ~3,800 left this month). Safe to rerun: it skips files already saved.
Run from saif_local:  python pull_qb_history.py   -> qb_history.zip (attach it back to Claude)."""
import json, os, time, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parent
def load_env(path=HERE / '.env'):
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); v = v.strip().strip('"').strip("'")
                if v: os.environ.setdefault(k.strip(), v)
load_env()
key = os.environ.get('CFBD_API_KEY', '').strip()
if not key: raise SystemExit('CFBD_API_KEY not found in .env')

def get(path):
    req = Request('https://api.collegefootballdata.com' + path,
                  headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        return {'error': e.code, 'body': e.read().decode('utf-8', 'replace')[:200]}

out = HERE / 'qb_history'; out.mkdir(exist_ok=True)
jobs = []
for y in (2023, 2024, 2025):
    jobs.append((f'ppa_QB_{y}', f'/ppa/players/season?year={y}&position=QB'))
    for wk in range(1, 16):
        jobs.append((f'passing_{y}_w{wk:02d}',
                     f'/games/players?year={y}&week={wk}&seasonType=regular&category=passing'))
used = 0
for name, path in jobs:
    f = out / f'{name}.json'
    if f.exists() and f.stat().st_size > 50:
        continue
    data = get(path); used += 1
    f.write_text(json.dumps(data), encoding='utf-8')
    print(f'{name:22s}', f'rows={len(data)}' if isinstance(data, list) else data)
    time.sleep(0.3)
print(f'\nCFBD calls used this run: {used}')
zp = HERE / 'qb_history.zip'
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(out.glob('*.json')): z.write(f, f.name)
print(f'Done. Attach {zp} back to Claude ({zp.stat().st_size/1e6:.1f} MB).')
