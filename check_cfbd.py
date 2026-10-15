"""Print your CFBD plan level and remaining calls. Run from saif_local:  python check_cfbd.py
Reads CFBD_API_KEY from .env (or the environment). The key is never printed."""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def load_env(path=Path(__file__).resolve().parent / '.env'):
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                v = v.strip().strip('"').strip("'")
                if v:
                    os.environ.setdefault(k.strip(), v)

load_env()
key = os.environ.get('CFBD_API_KEY', '').strip()
if not key:
    raise SystemExit('CFBD_API_KEY not found in .env')

def get(path):
    req = Request('https://api.collegefootballdata.com' + path,
                  headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:200]

print('/info ->', get('/info'))
# does the key reach the player endpoints we want for QB/RB injury impact?
for name, path in [('player PPA', '/ppa/players/season?year=2026&position=QB&team=Ohio'),
                   ('player usage', '/player/usage?year=2026&team=Ohio&position=QB'),
                   ('weather', '/games/weather?year=2026&week=7')]:
    code, body = get(path)
    n = len(body) if isinstance(body, list) else '-'
    print(f'{name:13s} HTTP {code}  rows: {n}' + ('' if code == 200 else f'  {body}'))
