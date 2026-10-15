"""Second CFBD probe: historical weather (for the backtest) + week-window player PPA (to detect
players who missed recent games) + one week of per-game player stats. About 8 CFBD calls.
Run from saif_local:  python probe2_cfbd.py    -> makes probe2_out.zip, attach it back to Claude."""
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
        with urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        return {'error': e.code, 'body': e.read().decode('utf-8', 'replace')[:300]}

out = HERE / 'probe2_out'; out.mkdir(exist_ok=True)
calls = {
    'weather_2023':        '/games/weather?year=2023&seasonType=regular',
    'weather_2024':        '/games/weather?year=2024&seasonType=regular',
    'weather_2025':        '/games/weather?year=2025&seasonType=regular',
    'ppa_QB_2026_thru_w3': '/ppa/players/season?year=2026&position=QB&endWeek=3',
    'ppa_QB_2026_thru_w6': '/ppa/players/season?year=2026&position=QB&endWeek=6',
    'usage_QB_2026_thru_w3': '/player/usage?year=2026&position=QB&endWeek=3',
    'games_players_w6':    '/games/players?year=2026&week=6&seasonType=regular&category=passing',
}
for name, path in calls.items():
    data = get(path)
    (out / f'{name}.json').write_text(json.dumps(data), encoding='utf-8')
    print(f'{name:24s}', f'rows={len(data)}' if isinstance(data, list) else data)

zp = HERE / 'probe2_out.zip'
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in out.glob('*.json'): z.write(f, f.name)
print(f'\nDone. Attach {zp} back to Claude.')
