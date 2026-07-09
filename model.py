import os
import json
from datetime import datetime, timezone

from api import collect_all_games

APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = f'{APP_DIR}/data'

ELO_BASE = 1500
HOME_ADVANTAGE = 0
K_BASE = 20
ELO_WEIGHT = 0.40
PYTH_WEIGHT = 0.40
RECENT_WEIGHT = 0.20
PYTH_SCALE = 600
RECENT_SCALE = 400
MLB_AVG_ERA = 4.20
ERA_TO_ELO = 15
MAX_PITCHER_ADJ = 30
REST_FACTOR = 3
PARK_WEIGHT = 50
MAX_PARK_ADJ = 15
BULLPEN_WEIGHT = 5
MAX_BULLPEN_ADJ = 15

SPORT = 'baseball'
LEAGUE = 'mlb'
SEASON = 2026
PYTH_EXP = 2.0


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def compute_league_avg_era(teams_dict):
    total, count = 0, 0
    for td in teams_dict.values():
        s = td['stats']
    for stat_name in ('avgPointsAgainst', 'era', 'earnedRunAverage', 'teamEra'):
        if stat_name in s:
            try:
                total += float(s[stat_name])
                count += 1
            except ValueError:
                pass
            break
    return total / count if count > 0 else MLB_AVG_ERA


def compute_elo(games, teams_dict):
    elo = {abbr: ELO_BASE for abbr in teams_dict}
    completed = sorted(
        [g for g in games if g['status'] == 'Final'
         and g['team_score'] is not None and g['opp_score'] is not None],
        key=lambda g: g['date']
    )
    for g in completed:
        a, h = g['away_abbr'], g['home_abbr']
        a_s, h_s = g['away_score'], g['home_score']
        ra, rh = elo[a], elo[h]

        e_away = 1.0 / (1.0 + 10.0 ** ((rh + HOME_ADVANTAGE - ra) / 400.0))
        k = K_BASE * (2.2 / (abs(ra - rh) * 0.001 + 2.2)) * (0.5 + abs(h_s - a_s) / 50)
        k = min(k, K_BASE * 3)
        s_a, s_h = (0.0, 1.0) if h_s > a_s else ((1.0, 0.0) if a_s > h_s else (0.5, 0.5))
        elo[a] = ra + k * (s_a - e_away)
        elo[h] = rh + k * (s_h - (1 - e_away))
    return elo


def compute_team_stats(abbr, td, completed_games, elo, league_avg_era):
    s = td['stats']
    def safe_float(v, default=0):
        try:
            return float(v or 0)
        except (ValueError, TypeError):
            return default
    pf = safe_float(s.get('pointsFor'))
    pa = safe_float(s.get('pointsAgainst'))
    wins = safe_float(s.get('wins'))
    losses = safe_float(s.get('losses'))
    total = wins + losses
    win_pct = wins / total if total > 0 else 0.5

    pyth_wp = (pf ** PYTH_EXP) / (pf ** PYTH_EXP + pa ** PYTH_EXP) if pf + pa > 0 else win_pct

    team_games = sorted(
        [g for g in completed_games if g['team_abbr'] == abbr and g['won'] is not None],
        key=lambda x: x['date'], reverse=True
    )[:10]
    recent_wins = sum(1 for g in team_games if g['won'])
    recent_total = len(team_games)
    recent_wp = recent_wins / recent_total if recent_total > 0 else win_pct

    last_game = team_games[0] if team_games else None
    if last_game:
        try:
            dt = datetime.fromisoformat(last_game['date'].replace('Z', '+00:00'))
            rest_days = (datetime.now(timezone.utc) - dt).total_seconds() / 3600 / 24
        except Exception:
            rest_days = 3
    else:
        rest_days = 3

    rating_elo = elo[abbr]
    rating_pyth = ELO_BASE + (pyth_wp - 0.5) * PYTH_SCALE
    rating_recent = ELO_BASE + (recent_wp - 0.5) * RECENT_SCALE
    rating = (rating_elo * ELO_WEIGHT + rating_pyth * PYTH_WEIGHT
              + rating_recent * RECENT_WEIGHT)

    home_wp_extra = 0
    hw = float(s.get('homeWins', 0) or 0)
    hl = float(s.get('homeLosses', 0) or 0)
    rw = float(s.get('roadWins', 0) or 0)
    rl = float(s.get('roadLosses', 0) or 0)
    if hw + hl > 0 and rw + rl > 0:
        home_wp_extra = (hw / (hw + hl)) - (rw / (rw + rl))

    team_era = None
    for stat_name in ('avgPointsAgainst', 'era', 'earnedRunAverage', 'teamEra'):
        if stat_name in s:
            try:
                team_era = float(s[stat_name])
            except ValueError:
                pass
            break
    bullpen_adj = clamp(
        (league_avg_era - team_era) * BULLPEN_WEIGHT if team_era and team_era > 0 else 0,
        -MAX_BULLPEN_ADJ, MAX_BULLPEN_ADJ
    )

    record = s.get('overall', '')
    if not record:
        w = int(s.get('wins', 0))
        l = int(s.get('losses', 0))
        otl = int(s.get('otLosses', 0) or 0)
        record = f'{w}-{l}-{otl}' if otl else f'{w}-{l}'

    return {
        'name': td['name'],
        'rating': rating,
        'record': record,
        'win_pct': win_pct,
        'rest_days': rest_days,
        'streak': s.get('streak', ''),
        'home_wp_extra': home_wp_extra,
        'bullpen_adj': bullpen_adj,
    }


def compute_ratings(teams_dict, sport, league, season):
    all_games = collect_all_games(teams_dict, sport, league, season)
    if not all_games:
        return {}

    completed = [g for g in all_games if g['status'] == 'Final'
                 and g['team_score'] is not None and g['opp_score'] is not None]

    league_avg_era = compute_league_avg_era(teams_dict)
    elo = compute_elo(all_games, teams_dict)

    return {
        abbr: compute_team_stats(abbr, td, completed, elo, league_avg_era)
        for abbr, td in teams_dict.items()
    }


def win_prob(rating_a, rating_b, home_extra=0, adj_a=0, adj_b=0):
    return 1.0 / (1.0 + 10.0 ** ((rating_b + adj_b - rating_a - adj_a - HOME_ADVANTAGE - home_extra) / 400.0))
