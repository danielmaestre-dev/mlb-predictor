import os
import json
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

PERU_TZ = timezone(timedelta(hours=-5))

import requests
import requests_cache
from requests import ConnectionError, Timeout

APP_DIR = os.path.expanduser('~/.mlbpredictor')
DATA_DIR = f'{APP_DIR}/data'
PARK_FACTORS_PATH = f'{DATA_DIR}/park_factors.json'

session = requests_cache.CachedSession(f'{APP_DIR}/cache/http_cache', expire_after=3600)


def load_park_factors():
    try:
        with open(PARK_FACTORS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def clean_name(name):
    parts = name.split()
    if len(parts) >= 2 and parts[0] == parts[-1]:
        return ' '.join(parts[:-1])
    return name


def extract_pitcher(comp):
    probables = comp.get('probables', [])
    for p in probables:
        athlete = p.get('athlete', {})
        era = None
        stats = p.get('statistics', [])
        if isinstance(stats, list):
            for s in stats:
                if isinstance(s, dict) and s.get('name') == 'ERA':
                    try:
                        era = float(s.get('displayValue', '0'))
                    except ValueError:
                        era = None
        return {'name': athlete.get('displayName', ''), 'era': era}
    return {}


def fetch_json(url, params=None, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                raise RuntimeError(f'HTTP {r.status_code} for {url}')
            return r.json()
        except (requests.RequestException, ConnectionError, Timeout, RuntimeError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise last_err


def american_to_prob(odds_str):
    try:
        odds = int(odds_str)
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    except (ValueError, TypeError):
        return None


def american_to_decimal(odds_str):
    try:
        odds = int(odds_str)
        if odds > 0:
            return 1 + odds / 100
        else:
            return 1 + 100 / abs(odds)
    except (ValueError, TypeError):
        return None


def get_standings(sport, league, season):
    try:
        data = fetch_json(
            f'https://site.web.api.espn.com/apis/v2/sports/{sport}/{league}/standings',
            {'season': season}
        )
    except Exception:
        data = None

    teams = {}

    def extract(node):
        if 'standings' in node and 'entries' in node['standings']:
            for entry in node['standings']['entries']:
                team = entry['team']
                stats = {}
                for s in entry.get('stats', []):
                    if 'value' in s:
                        stats[s['name']] = s.get('displayValue', s['value'])
                for extra_key in ('teamStats', 'statistics', 'overallStats'):
                    extra = entry.get(extra_key, {})
                    if isinstance(extra, dict):
                        for cat_key, cat_val in extra.items():
                            if isinstance(cat_val, dict):
                                for stat_name, stat_val in cat_val.items():
                                    if isinstance(stat_val, dict) and 'value' in stat_val:
                                        stats[f'{cat_key}.{stat_name}'] = str(stat_val['value'])
                teams[team['abbreviation']] = {
                    'id': team['id'],
                    'name': team['displayName'],
                    'stats': stats,
                }
        for child in node.get('children', []):
            extract(child)

    if data:
        extract(data)
    return teams


def fetch_team_schedule(teams_dict, sport, league, team_abbr, season):
    team_id = teams_dict[team_abbr]['id']
    url = f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule'
    try:
        data = fetch_json(url, {'season': season})
    except Exception:
        return []

    games = []
    for ev in data.get('events', []):
        comp = ev['competitions'][0]
        competitors = comp.get('competitors', [])
        if len(competitors) < 2:
            continue
        try:
            away = next(c for c in competitors if c['homeAway'] == 'away')
            home = next(c for c in competitors if c['homeAway'] == 'home')
        except StopIteration:
            continue
        a, h = away['team']['abbreviation'], home['team']['abbreviation']
        if a not in teams_dict or h not in teams_dict:
            continue

        def get_score(c):
            s = c.get('score', {})
            return s.get('value') if isinstance(s, dict) else None

        games.append({
            'id': ev['id'],
            'date': ev.get('date', ''),
            'away_abbr': a,
            'home_abbr': h,
            'away_score': get_score(away),
            'home_score': get_score(home),
            'status': comp['status']['type']['description'],
            'is_home': h == team_abbr,
            'team_abbr': team_abbr,
            'opponent_abbr': h if a == team_abbr else a,
            'team_score': get_score(home) if h == team_abbr else get_score(away),
            'opp_score': get_score(away) if h == team_abbr else get_score(home),
            'won': None,
        })
        g = games[-1]
        if g['team_score'] is not None and g['opp_score'] is not None:
            g['won'] = g['team_score'] > g['opp_score']
    return games


def collect_all_games(teams_dict, sport, league, season):
    all_by_id = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        fs = {ex.submit(fetch_team_schedule, teams_dict, sport, league, abbr, season): abbr
              for abbr in teams_dict}
        for f in as_completed(fs):
            try:
                for g in f.result():
                    if g['id'] not in all_by_id:
                        all_by_id[g['id']] = g
            except Exception:
                pass
    return list(all_by_id.values())


def get_games(sport, league, valid_abbrevs, limit=15):
    now_peru = datetime.now(PERU_TZ)
    today = now_peru.strftime('%Y%m%d')
    today_fmt = now_peru.strftime('%Y-%m-%d')

    games_data = []
    try:
        data = fetch_json(
            f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard',
            {'dates': today}
        )
        games_data.extend(data.get('events', []))
    except Exception:
        pass

    def get_score(c):
        s = c.get('score', {})
        return s.get('value') if isinstance(s, dict) else None

    games = []
    for ev in games_data:
        comp = ev['competitions'][0]
        st = ev.get('season', {}).get('type', 0)
        if st not in (2, 3):
            continue
        if ev.get('date', '')[:10] != today_fmt:
            continue
        competitors = comp.get('competitors', [])
        if len(competitors) < 2:
            continue
        away = next(c for c in competitors if c['homeAway'] == 'away')
        home = next(c for c in competitors if c['homeAway'] == 'home')
        a, h = away['team']['abbreviation'], home['team']['abbreviation']
        if a not in valid_abbrevs or h not in valid_abbrevs:
            continue

        state = comp['status']['type']['state']
        is_completed = (state == 'post')
        is_in_progress = (state == 'in')

        away_name = clean_name(away['team']['displayName'])
        home_name = clean_name(home['team']['displayName'])

        home_score = get_score(home)
        away_score = get_score(away)
        actual_winner = None
        if is_completed:
            actual_winner = next((c['team']['abbreviation'] for c in competitors if c.get('winner', False)), None)

        away_pitcher = extract_pitcher(away)
        home_pitcher = extract_pitcher(home)

        odds = comp.get('odds', [])
        p_home_mkt = p_away_mkt = None
        home_odds_str = ''
        away_odds_str = ''
        if odds:
            ml = odds[0].get('moneyline', {})
            home_odds_str = ml.get('home', {}).get('close', {}).get('odds', '')
            away_odds_str = ml.get('away', {}).get('close', {}).get('odds', '')
            p_h = american_to_prob(home_odds_str)
            p_a = american_to_prob(away_odds_str)
            if p_h and p_a and (p_h + p_a) > 0:
                vig = p_h + p_a
                p_home_mkt = p_h / vig * 100
                p_away_mkt = p_a / vig * 100

        games.append({
            'id': ev['id'],
            'date': ev.get('date', ''),
            'away_abbr': a,
            'away_name': away_name,
            'home_abbr': h,
            'home_name': home_name,
            'p_home_mkt': p_home_mkt,
            'p_away_mkt': p_away_mkt,
            'away_pitcher': away_pitcher,
            'home_pitcher': home_pitcher,
            'home_odds_str': home_odds_str,
            'away_odds_str': away_odds_str,
            'venue': comp.get('venue', {}).get('fullName', ''),
            'completed': is_completed,
            'in_progress': is_in_progress,
            'home_score': home_score,
            'away_score': away_score,
            'actual_winner': actual_winner,
            'status_desc': comp['status']['type'].get('description', ''),
        })
        if len(games) >= limit:
            break
    return games
