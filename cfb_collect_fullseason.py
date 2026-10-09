"""Click Run in your editor to collect CFBD historical features.
Uses only Python's standard library: no pandas, numpy, requests or sklearn.
Saves a results ZIP beside this script. Upload it for the model comparison.
Reads CFBD_API_KEY or asks for the key privately. No key is saved.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import time
import zipfile
import sys
import shutil
import csv
from collections import Counter
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

BASE = 'https://api.collegefootballdata.com'
CORE = ['ppa','successRate','explosiveness','pointsPerOpportunity','havoc.total']
EXTRA = ['passingPlays.ppa','rushingPlays.ppa','passingPlays.successRate',
         'rushingPlays.successRate','passingPlays.explosiveness',
         'rushingPlays.explosiveness','passingPlays.rate','rushingPlays.rate',
         'standardDowns.ppa','passingDowns.ppa','powerSuccess','stuffRate',
         'lineYards','secondLevelYards','openFieldYards',
         'fieldPosition.averageStart','havoc.frontSeven','havoc.db']

def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)

def atomic_csv(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    tmp = path.with_suffix('.csv.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)

def flat(obj, prefix=''):
    result={}
    for key,value in obj.items():
        name=f'{prefix}.{key}' if prefix else key
        if isinstance(value,dict):result.update(flat(value,name))
        else:result[name]=value
    return result

def number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):return None

def numeric_profile(row):
    return {k:number(v) for k,v in row.items()
            if k.startswith(('offense.','defense.')) and number(v) is not None}

def team_index(rows):
    result={}
    for raw in rows:
        row=flat(raw);team=row.get('team')
        if not team:raise ValueError('Advanced-stat response is missing team.')
        if team in result:raise ValueError(f'Duplicate team in advanced snapshot: {team}')
        result[team]=numeric_profile(row)
    if rows and not any(result.values()):raise ValueError('No numeric offense/defense fields in advanced response.')
    return result

def counting_index(rows):
    result={}
    for row in rows:
        team,stat=row.get('team'),row.get('statName')
        if not team or not stat:raise ValueError('Counting response lacks team/statName.')
        values=result.setdefault(team,{})
        if stat in values:raise ValueError(f'Duplicate counting stat: {team}/{stat}')
        values[stat]=number(row.get('statValue'))
    return result

def blend(current, prior, games, prior_games):
    """Use identical per-stat game-count blending at every historical cutoff.

    Missing prior: use current. Missing current with games > 0: unavailable.
    No current games: use prior. Does not treat missing rates as zero.
    """
    result={}
    for key in current.keys() | prior.keys():
        c,p=number(current.get(key)),number(prior.get(key))
        # Preserve cumulative quantities in current/prior columns only.
        leaf=key.rsplit('.',1)[-1].lower()
        if leaf in {'plays','drives','totalppa','totalopportunities','totalopportunies'} or (leaf.startswith('total') and key != 'offense.havoc.total' and key != 'defense.havoc.total'):
            continue
        if prior_games==0:result[key]=c
        elif games==0:result[key]=p
        elif c is None:result[key]=None
        elif p is None:result[key]=c
        else:result[key]=(prior_games*p+games*c)/(prior_games+games)
    return result

def net_difference(home,away,stat):
    ho,hd,ao,ad=[number(d.get(f'{side}.{stat}')) for d,side in
                 [(home,'offense'),(home,'defense'),(away,'offense'),(away,'defense')]]
    if any(x is None for x in [ho,hd,ao,ad]):return None
    value=(ho+ad)-(ao+hd)
    return -value if stat.startswith('havoc.') or stat in {'stuffRate','fieldPosition.averageStart'} else value

def turnover_margin(counts):
    games=number(counts.get('games'));lost=number(counts.get('turnovers'));won=number(counts.get('turnoversOpponent'))
    return (won-lost)/games if games and lost is not None and won is not None else None

def choose_line(rows,providers):
    indexed={r['provider']:r for r in rows if r.get('provider')}
    for provider in providers:
        row=indexed.get(provider)
        if row and number(row.get('spread')) is not None:
            return {'line_provider':provider,'market_spread':number(row.get('spread')),
                    'opening_spread':number(row.get('spreadOpen')),
                    'market_total':number(row.get('overUnder')),
                    'opening_total':number(row.get('overUnderOpen'))}
    return {'line_provider':None,'market_spread':None,'opening_spread':None,
            'market_total':None,'opening_total':None}

def parse_date(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None

class Client:
    def __init__(self,cache,offline=False):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.offline=offline;self.key=os.environ.get('CFBD_API_KEY','').strip()
        self.calls=0

    def get(self,endpoint,params):
        identity={'endpoint':endpoint,'params':params}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        path=self.cache/f'{digest}.json'
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved['request']!=identity:raise ValueError('Cache request mismatch')
            return saved['data']
        if self.offline:raise RuntimeError(f'Missing offline cache for {endpoint} {params}')
        if not self.key:
            self.key=getpass.getpass('CFBD API key (hidden; not saved): ').strip()
            if not self.key:raise RuntimeError('No API key supplied.')
        for attempt in range(5):
            request = Request(BASE + endpoint + '?' + urlencode(params),
                              headers={'Authorization': 'Bearer ' + self.key,
                                       'Accept': 'application/json'})
            try:
                self.calls += 1
                with urlopen(request, timeout=45) as response:
                    data = json.load(response)
            except HTTPError as error:
                status = error.code
                error.close()
                if status in (401, 403):
                    raise RuntimeError(f'HTTP {status} for {endpoint}: check key and endpoint access.') from None
                if status == 429 or status >= 500:
                    if attempt < 4:
                        time.sleep(min(2 ** attempt, 16))
                        continue
                    raise RuntimeError(f'HTTP {status} for {endpoint}; rerun later to resume.') from None
                raise RuntimeError(f'HTTP {status} for {endpoint}; request stopped.') from None
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 4:
                    raise RuntimeError(f'Connection failed for {endpoint}; cached progress is safe.') from None
                time.sleep(min(2 ** attempt, 16))
                continue
            if not isinstance(data, list):
                raise ValueError(f'Unexpected response shape for {endpoint}; expected a list.')
            atomic_json(path, {'request': identity,
                              'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                              'data': data})
            time.sleep(.3)
            return data
        raise RuntimeError('Retry limit reached.')


def make_row(game,year,week,current,counts,prior,prior_counts,prior_weight,lines,providers,schedule):
    home,away=game['homeTeam'],game['awayTeam']
    row={'game_id':game['id'],'season':year,'week':week,'stats_through_week':week-1,
         'home_team':home,'away_team':away,'kickoff_utc':game.get('startDate'),
         'neutral_site':game.get('neutralSite'),'venue_id':game.get('venueId'),
         'conference_game':game.get('conferenceGame'),'prior_weight_games':prior_weight,
         'actual_margin':None,'actual_total':None}
    hp,ap=number(game.get('homePoints')),number(game.get('awayPoints'))
    if game.get('completed') is True and hp is not None and ap is not None:
        row.update(actual_margin=hp-ap,actual_total=hp+ap)
    row['feature_period'] = 'early' if week <= 3 else 'later'
    row['current_stats_policy'] = 'prior_only' if week <= 1 else 'through_previous_api_week'
    if week <= 1: row['stats_through_week'] = None
    row['home_classification'] = game.get('homeClassification')
    row['away_classification'] = game.get('awayClassification')
    row.update(choose_line(lines.get(game['id'],[]),providers))
    profiles={};target_time=parse_date(game.get('startDate'))
    for side,team in [('home',home),('away',away)]:
        c=current.get(team,{});p=prior.get(team,{})
        cnt=counts.get(team,{});pcnt=prior_counts.get(team,{})
        n=number(cnt.get('games'))
        # Opening API weeks deliberately use prior-season profiles only.
        if week <= 1:
            c = {}; cnt = {'games': 0.0}; n = 0.0
        elif n is None:
            earlier = [g for g in schedule if team in [g.get('homeTeam'), g.get('awayTeam')]
                       and g.get('week', 999) < week
                       and g.get('completed') is True]
            if earlier:
                raise ValueError(f'{team}: games count unavailable despite earlier completed games')
            c = {}; cnt = {'games': 0.0}; n = 0.0
        b=blend(c,p,n,prior_weight);profiles[side]=b
        row[f'{side}.games_before']=n
        row[f'{side}.prior_available']=bool(p)
        for kind,profile in [('current',c),('prior',p),('blended',b)]:
            row.update({f'{side}.{kind}.{key}':value for key,value in profile.items()})
        row.update({f'{side}.count.{key}':value for key,value in cnt.items()})
        row.update({f'{side}.prior_count.{key}':value for key,value in pcnt.items()})
        t=blend({'turnover_margin':turnover_margin(cnt)},
                {'turnover_margin':turnover_margin(pcnt)},n,prior_weight).get('turnover_margin')
        row[f'{side}.blended.turnover_margin']=t
        times=[]
        for g in schedule:
            if team not in [g.get('homeTeam'),g.get('awayTeam')]:continue
            if g.get('week',999)>=week or g.get('completed') is not True:continue
            d=parse_date(g.get('startDate'))
            if d and target_time and d>=target_time:
                raise ValueError(f'{team}: prior-week game occurs at/after target kickoff; weekly cutoff unsafe')
            if d:times.append(d)
        row[f'{side}.rest_days']=((target_time-max(times)).total_seconds()/86400 if target_time and times else None)
    for stat in CORE+EXTRA:
        row['diff_'+stat.replace('.','_')]=net_difference(profiles['home'],profiles['away'],stat)
    h,a=row['home.blended.turnover_margin'],row['away.blended.turnover_margin']
    row['diff_turnover_margin']=h-a if h is not None and a is not None else None
    h,a=row['home.rest_days'],row['away.rest_days']
    row['rest_difference']=h-a if h is not None and a is not None else None
    row['earlier_same_week_games'] = sum(
        g.get('id') != game['id'] and g.get('week') == week
        and g.get('completed') is True
        and (home in [g.get('homeTeam'),g.get('awayTeam')] or away in [g.get('homeTeam'),g.get('awayTeam')])
        and parse_date(g.get('startDate')) is not None and target_time is not None
        and parse_date(g['startDate']) < target_time for g in schedule)
    return row

def pull(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    config={'schema_version':2,'years':args.years,'start_week':args.start_week,
            'end_week':args.end_week,'prior_weight':args.prior_weight,'providers':args.providers}
    configfile=out/'config.json'
    if configfile.exists() and json.loads(configfile.read_text())!=config:
        raise ValueError('Output folder has a different configuration. Choose a new --out folder.')
    atomic_json(configfile,config)
    # Reuse completed requests without changing the previous dataset.
    reused = 0
    old_cache = Path(args.cache_source) / 'raw'
    (out / 'raw').mkdir(exist_ok=True)
    if old_cache.exists():
        for source in old_cache.glob('*.json'):
            target = out / 'raw' / source.name
            if not target.exists():
                shutil.copy2(source, target); reused += 1
    print(f'Reused {reused} cached responses.', flush=True)
    client=Client(out/'raw',args.offline);allrows=[];issues=[]
    # Required to construct pre-2022 opponent-adjusted team priors.
    client.get('/games', {'year':min(args.years)-1,'seasonType':'regular'})
    week_labels = []
    for year in args.years:
        print(f'{year}: loading prior season and schedule',flush=True)
        prior=team_index(client.get('/stats/season/advanced',{'year':year-1})) if args.prior_weight else {}
        pc= counting_index(client.get('/stats/season',{'year':year-1})) if args.prior_weight else {}
        schedule=client.get('/games',{'year':year,'seasonType':'regular'})
        weeks = sorted({g['week'] for g in schedule
                        if args.start_week <= g.get('week',-1) <= args.end_week})
        week_labels.append({'season':year,'api_weeks':weeks,
                            'first_kickoff':min(g['startDate'] for g in schedule if g.get('startDate'))})
        atomic_json(out/'week_labels.json',week_labels)
        for week in weeks:
            description = 'prior-season inputs only' if week <= 1 else f'stats through week {week-1}'
            print(f'{year} week {week}: {description}',flush=True)
            if week <= 1:
                # Never issue endWeek=0: no current-year aggregates for opening API weeks.
                adv = {}; counts = {}
            else:
                adv=team_index(client.get('/stats/season/advanced',{'year':year,'endWeek':week-1}))
                counts=counting_index(client.get('/stats/season',{'year':year,'endWeek':week-1}))
            # Independently check weekly truncation using counting games and the schedule.
            for team,c in counts.items():
                scheduled=sum(g.get('completed') is True and g.get('week',999)<week and
                              team in [g.get('homeTeam'),g.get('awayTeam')] for g in schedule)
                if c.get('games') is not None and c['games']>scheduled:
                    raise ValueError(f'{team}: games count {c["games"]} exceeds {scheduled} completed prior-week games. Check API cutoff semantics.')
            rawlines=client.get('/lines',{'year':year,'week':week,'seasonType':'regular'})
            lines={g['id']:g.get('lines',[]) for g in rawlines}
            rows=[]
            for game in schedule:
                if game.get('week')!=week:continue
                if game.get('homeClassification')!='fbs' or game.get('awayClassification')!='fbs':continue
                try:rows.append(make_row(game,year,week,adv,counts,prior,pc,args.prior_weight,lines,args.providers,schedule))
                except ValueError as e:issues.append({'game_id':game.get('id'),'season':year,'week':week,'reason':str(e)})
            atomic_csv(out/'weekly'/f'{year}_w{week}.csv',rows)
            allrows.extend(rows)
            atomic_csv(out/'expanded_features.csv',allrows)
            atomic_json(out/'excluded_rows.json',issues)
    if not allrows:
        raise ValueError('No game rows produced. Inspect cache and exclusions.')
    keys = [(row['season'], row['game_id']) for row in allrows]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate game IDs in final data.')
    columns = list(dict.fromkeys(key for row in allrows for key in row))
    dictionary = []
    for column in columns:
        present = sum(row.get(column) is not None for row in allrows)
        dictionary.append({'column': column, 'non_missing': present,
                           'missing': len(allrows) - present})
    atomic_json(out / 'field_inventory.json', dictionary)
    atomic_json(out / 'run_summary.json',
                {'rows': len(allrows), 'columns': len(columns),
                 'excluded': len(issues), 'network_requests_this_run': client.calls,
                 'seasons': dict(Counter(row['season'] for row in allrows)),
                 'mode': 'fullseason_standard_library_collection',
                 'period_rows': dict(Counter(row['feature_period'] for row in allrows)),
                 'cached_responses_copied': reused})
    print(f'Saved {len(allrows)} games, {len(columns)} columns. Excluded {len(issues)} games.', flush=True)
    package(out)


def package(folder):
    folder=Path(folder);archive=folder.parent/(folder.name+'_results.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and not path.name.endswith('.tmp'):
                z.write(path,str(Path(folder.name)/path.relative_to(folder)))
    print(f'Upload this file back to ChatGPT: {archive.resolve()}')

def main():
    # Changed from 'cfb_fullseason_data' to a new folder name on purpose:
    # pull() hard-stops if an existing --out folder was built with a
    # different years/week config (see the config.json check in pull()).
    # Since we're adding 2026, reusing the old folder name would just throw
    # "Output folder has a different configuration." New folder name avoids that.
    out = Path(__file__).resolve().parent / 'cfb_fullseason_data_2026'
    print('Collecting historical data using built-in Python tools.', flush=True)
    print(f'Output folder: {out}', flush=True)
    args = argparse.Namespace(out=str(out), years=[2022, 2023, 2024, 2025, 2026],
                              start_week=0, end_week=14, prior_weight=4,
                              providers=['Bovada', 'ESPN Bet'], offline=False,
                              cache_source=str(Path(__file__).resolve().parent/'cfb_expanded_data'))
    pull(args)
    print('DONE. Upload cfb_fullseason_data_2026_results.zip for the backtest.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        raise SystemExit('Stopped. Click Run again to resume cached progress.') from None

