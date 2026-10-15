"""Pull small sample data for the QB/RB injury and weather work. Uses ~6 CFBD calls.
Run from saif_local:  python probe_cfbd.py     -> writes probe_out/*.json and prints a summary.
Then attach the probe_out folder's files (or the one ZIP it makes) back to Claude."""
import json, os, zipfile
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
        with urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        return {'error': e.code, 'body': e.read().decode('utf-8', 'replace')[:300]}

out = HERE / 'probe_out'; out.mkdir(exist_ok=True)
calls = {
    'ppa_players_QB_2026':   '/ppa/players/season?year=2026&position=QB',
    'ppa_players_RB_2026':   '/ppa/players/season?year=2026&position=RB',
    'usage_QB_2026':         '/player/usage?year=2026&position=QB',
    'usage_RB_2026':         '/player/usage?year=2026&position=RB',
    'weather_week7_2026':    '/games/weather?year=2026&week=7',
    'weather_week6_2026':    '/games/weather?year=2026&week=6',
}
for name, path in calls.items():
    data = get(path)
    (out / f'{name}.json').write_text(json.dumps(data), encoding='utf-8')
    if isinstance(data, list):
        print(f'{name:22s} rows={len(data):5d}  keys={sorted(data[0].keys()) if data else []}')
    else:
        print(f'{name:22s} {data}')

w = json.loads((out / 'weather_week7_2026.json').read_text())
if isinstance(w, list) and w:
    filled = {k: sum(1 for r in w if r.get(k) is not None) for k in w[0] if k not in ('id',)}
    print('\nweather week 7: non-null counts ->', filled)
    print('example row:', w[0])

zp = HERE / 'probe_out.zip'
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in out.glob('*.json'): z.write(f, f.name)
print(f'\nDone. Attach {zp} back to Claude.')
