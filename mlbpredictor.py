#!/usr/bin/env python3
import os
import json
import subprocess
import sys
from datetime import datetime, timedelta

from api import (
    get_games, get_standings, fetch_json, load_park_factors, american_to_decimal
)
from model import (
    compute_ratings, win_prob, clamp, ELO_BASE, ERA_TO_ELO, MAX_PITCHER_ADJ,
    MLB_AVG_ERA, REST_FACTOR, PARK_WEIGHT, MAX_PARK_ADJ,
    SPORT, LEAGUE, SEASON
)
from display import console, display_table, write_log
from report import generate as generate_report, open_report

APP_DIR = os.path.expanduser('~/.mlbpredictor')
DATA_DIR = f'{APP_DIR}/data'
HISTORY_FILE = f'{DATA_DIR}/history.json'
SIMPLE = not sys.stdout.isatty() or 'FLATPAK_ID' in os.environ or '--simple' in sys.argv


def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return {'predictions': {}, 'stats': {'total': 0, 'correct': 0, 'accuracy': 0}}


def save_history(history):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def recalc_stats(history):
    resolved = [p for p in history.get('predictions', {}).values() if p.get('resolved')]
    correct = sum(1 for p in resolved if p.get('actual_winner') == p.get('predicted_winner'))
    total = len(resolved)
    history['stats'] = {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0,
    }


def resolve_predictions(history, sport, league):
    unresolved = {gid: p for gid, p in history.get('predictions', {}).items()
                  if not p.get('resolved')}
    if not unresolved:
        return history

    year = datetime.now().strftime('%Y')
    dates_seen = set()
    for p in unresolved.values():
        gd = p.get('game_date', '')
        if gd and len(gd) >= 5:
            dates_seen.add(f'{year}{gd[:2]}{gd[3:5]}')

    for d in dates_seen:
        try:
            data = fetch_json(
                f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard',
                {'dates': d}
            )
            for ev in data.get('events', []):
                gid = ev['id']
                if gid not in unresolved:
                    continue
                comp = ev['competitions'][0]
                if comp['status']['type']['state'] != 'post':
                    continue
                winner = next((c for c in comp['competitors'] if c.get('winner', False)), None)
                if winner:
                    pred = history['predictions'][gid]
                    pred['actual_winner'] = winner['team']['abbreviation']
                    pred['resolved'] = True
        except Exception:
            pass

    recalc_stats(history)
    return history


def add_predictions_to_history(history, results):
    if 'predictions' not in history:
        history['predictions'] = {}
    for r in results:
        gid = r['game_id']
        if gid in history['predictions']:
            existing = history['predictions'][gid]
            if existing.get('diff') is None:
                for field in ('diff', 'p_home_mkt', 'p_away_mkt', 'ev_home', 'ev_away', 'ev', 'conf'):
                    existing[field] = r.get(field)
            continue
        winner = r['home_abbr'] if r['p_home'] >= r['p_away'] else r['away_abbr']
        winner_prob = r['p_home'] if r['p_home'] >= r['p_away'] else r['p_away']
        actual = r.get('actual_winner')
        history['predictions'][gid] = {
            'date_predicted': datetime.now().strftime('%Y-%m-%d'),
            'game_date': r['inicio'],
            'home_abbr': r['home_abbr'],
            'away_abbr': r['away_abbr'],
            'home_name': r['home_name'],
            'away_name': r['away_name'],
            'predicted_winner': winner,
            'predicted_prob': winner_prob,
            'actual_winner': actual if r.get('completed') else None,
            'resolved': bool(r.get('completed')),
            'diff': r.get('diff'),
            'p_home_mkt': r.get('p_home_mkt'),
            'p_away_mkt': r.get('p_away_mkt'),
            'ev_home': r.get('ev_home'),
            'ev_away': r.get('ev_away'),
            'ev': r.get('ev'),
            'conf': r.get('conf'),
        }
    recalc_stats(history)
    return history


def calculate_ev(model_prob, market_odds_str):
    dec = american_to_decimal(market_odds_str)
    if dec is None:
        return None
    ev = (model_prob / 100 * dec) - 1
    return ev * 100


def confidence_rating(model_prob, market_prob):
    if market_prob is None:
        return 'N/A'
    diff = abs(model_prob - market_prob)
    if diff < 3:
        return 'A'
    elif diff < 7:
        return 'B'
    elif diff < 12:
        return 'C'
    else:
        return 'D'


def status_msg(msg):
    if SIMPLE:
        print(f'MLB: {msg}...', flush=True)
    else:
        return msg

def predict_league():
    loading = SIMPLE
    status_ctx = None
    if not loading:
        status_ctx = console.status('[bold green]MLB: Cargando datos...[/]')
        status_ctx.__enter__()
        status = lambda msg: status_ctx.update(f'[bold green]{msg}[/]')
    else:
        print('MLB: Cargando datos...', flush=True)
        status = status_msg

    try:
        status('Standings')
        teams = get_standings(SPORT, LEAGUE, SEASON)
        if not teams:
            return []

        status('Calendarios (30 equipos)')
        ratings = compute_ratings(teams, SPORT, LEAGUE, SEASON)
        if not ratings:
            return []

        status('Partidos del dia')
        games = get_games(SPORT, LEAGUE, set(teams.keys()), limit=30)
        if not games:
            msg = 'MLB: Sin partidos proximos'
            if SIMPLE:
                print(msg)
            else:
                console.print(f'[bold green]{msg}[/]')
            return []

        status('Calculando probabilidades')
        park_factors = load_park_factors()

        results = []
        for g in games:
            ra = ratings.get(g['away_abbr'], {})
            rh = ratings.get(g['home_abbr'], {})

            rat_a = ra.get('rating', ELO_BASE)
            rat_h = rh.get('rating', ELO_BASE)

            rest_diff = rh.get('rest_days', 3) - ra.get('rest_days', 3)
            rest_bonus = rest_diff * REST_FACTOR
            home_extra = rh.get('home_wp_extra', 0) * 30 + rest_bonus

            away_pitcher = g.get('away_pitcher', {})
            home_pitcher = g.get('home_pitcher', {})
            away_era = away_pitcher.get('era')
            home_era = home_pitcher.get('era')
            away_pitcher_adj = clamp(
                (MLB_AVG_ERA - away_era) * ERA_TO_ELO if away_era is not None and away_era > 0 else 0,
                -MAX_PITCHER_ADJ, MAX_PITCHER_ADJ
            )
            home_pitcher_adj = clamp(
                (MLB_AVG_ERA - home_era) * ERA_TO_ELO if home_era is not None and home_era > 0 else 0,
                -MAX_PITCHER_ADJ, MAX_PITCHER_ADJ
            )

            away_bullpen = ra.get('bullpen_adj', 0)
            home_bullpen = rh.get('bullpen_adj', 0)

            home_pf = park_factors.get(g['home_abbr'], 1.0)
            park_adj = clamp((home_pf - 1.0) * PARK_WEIGHT, -MAX_PARK_ADJ, MAX_PARK_ADJ)

            total_home_adj = home_pitcher_adj + home_bullpen + park_adj
            total_away_adj = away_pitcher_adj + away_bullpen

            p_home = win_prob(rat_h, rat_a, home_extra=home_extra,
                              adj_a=total_home_adj, adj_b=total_away_adj) * 100
            p_away = 100 - p_home

            try:
                dt = datetime.fromisoformat(g['date'].replace('Z', '+00:00'))
                dt -= timedelta(hours=5)
                inicio = dt.strftime('%m-%d %H:%M')
            except Exception:
                inicio = g['date'][5:16].replace('T', ' ')

            diff = None
            ev_home = None
            ev_away = None
            if g.get('p_home_mkt') and g.get('p_away_mkt'):
                diff = (p_home - g['p_home_mkt']) if p_home >= p_away else (p_away - g['p_away_mkt'])
                ev_home = calculate_ev(p_home, g.get('home_odds_str', ''))
                ev_away = calculate_ev(p_away, g.get('away_odds_str', ''))

            pick_team = g['home_name'] if p_home >= p_away else g['away_name']
            pick_prob = p_home if p_home >= p_away else p_away
            pick_ev = ev_home if p_home >= p_away else ev_away
            pick_mkt = g['p_home_mkt'] if p_home >= p_away else g['p_away_mkt']
            conf = confidence_rating(pick_prob, pick_mkt)

            actual_winner = g.get('actual_winner')
            pick_result = None
            if actual_winner:
                pick_result = actual_winner == (g['home_abbr'] if p_home >= p_away else g['away_abbr'])

            results.append({
                'inicio': inicio,
                'game_id': g['id'],
                'away_name': g['away_name'],
                'home_name': g['home_name'],
                'away_abbr': g['away_abbr'],
                'home_abbr': g['home_abbr'],
                'away_record': ra.get('record', ''),
                'home_record': rh.get('record', ''),
                'p_away': p_away,
                'p_home': p_home,
                'p_away_mkt': g.get('p_away_mkt'),
                'p_home_mkt': g.get('p_home_mkt'),
                'diff': diff,
                'away_pitcher_name': away_pitcher.get('name', ''),
                'home_pitcher_name': home_pitcher.get('name', ''),
                'away_pitcher_era': away_pitcher.get('era'),
                'home_pitcher_era': home_pitcher.get('era'),
                'ev_home': ev_home,
                'ev_away': ev_away,
                'ev': pick_ev,
                'conf': conf,
                'pick_team': pick_team,
                'pick_prob': pick_prob,
                'venue': g.get('venue', ''),
                'completed': g.get('completed', False),
                'in_progress': g.get('in_progress', False),
                'home_score': g.get('home_score'),
                'away_score': g.get('away_score'),
                'actual_winner': actual_winner,
                'status_desc': g.get('status_desc', ''),
                'pick_result': pick_result,
            })

    finally:
        if status_ctx is not None:
            status_ctx.__exit__(None, None, None)

    display_table(results)
    return results


def run_prediction():
    try:
        subprocess.run(['git', '-C', APP_DIR, 'pull', 'origin', 'main'],
                      capture_output=True, timeout=30)
    except Exception:
        pass

    print('Predictor Deportivo - MLB')
    print('=' * 40)

    history = load_history()
    history = resolve_predictions(history, 'baseball', 'mlb')
    save_history(history)

    results = predict_league()
    if results:
        history = add_predictions_to_history(history, results)
        save_history(history)
        write_log(results, history)
        make_html_report(results, history)

    print()
    print('Datos: ESPN API | Cache: requests-cache (1h)')
    print('Modelo: Elo + Pythagorean + Forma + Descanso + Lanzador + Parque + Bullpen')
    print('Confianza: A(<3%) B(<7%) C(<12%) D(>12%) vs mercado | EV: Valor esperado')


def show_stats():
    subprocess.run([
        'python3', '-c',
        '''
import json, os, sys
from collections import OrderedDict
h = json.load(open(sys.argv[1]))
s = h["stats"]
preds = list(h.get("predictions", {}).values())
resolved = [p for p in preds if p.get("resolved")]
unresolved = [p for p in preds if not p.get("resolved")]
print(f"Predicciones guardadas: {len(preds)}")
print(f"Resueltas: {len(resolved)}")
print(f"Pendientes: {len(unresolved)}")
print()
if resolved:
    print(f"Precision global: {s['correct']}/{s['total']} ({s['accuracy']*100:.1f}%)")
    home_ok = sum(1 for p in resolved if p.get("actual_winner") == p.get("predicted_winner") and p.get("actual_winner") == p.get("home_abbr"))
    away_ok = sum(1 for p in resolved if p.get("actual_winner") == p.get("predicted_winner") and p.get("actual_winner") == p.get("away_abbr"))
    print(f"  Local: {home_ok} | Visita: {away_ok}")
    print()
    # group by date
    by_date = OrderedDict()
    for p in sorted(resolved, key=lambda x: x.get("game_date", "")):
        d = p.get("game_date", "??-??")[:5]
        by_date.setdefault(d, []).append(p)
    for date, games in by_date.items():
        date_ok = sum(1 for g in games if g.get("actual_winner") == g.get("predicted_winner"))
        date_total = len(games)
        date_pct = date_ok / date_total * 100
        date_home = sum(1 for g in games if g.get("actual_winner") == g.get("predicted_winner") == g.get("home_abbr"))
        date_away = date_ok - date_home
        print(f'=== {date} ({date_ok}/{date_total} - {date_pct:.0f}%, L:{date_home} V:{date_away}) ===')
        for p in games:
            w = chr(10003) if p["actual_winner"] == p["predicted_winner"] else chr(10007)
            print(f'  {p["game_date"]} {w} {p["away_name"]:22s} @ {p["home_name"]:22s} -> {p["predicted_winner"]} ({p["predicted_prob"]:.0f}%), real: {p["actual_winner"]}')
        print()
else:
    print("Aun sin partidos resueltos. Ejecuta la app manana.")
    if unresolved:
        print()
        print("Esperando:")
        for p in unresolved[:10]:
            print(f'  * {p["away_name"]} @ {p["home_name"]} ({p["game_date"]})')
        if len(unresolved) > 10:
            print(f'  ... y {len(unresolved)-10} mas')
''',
        HISTORY_FILE
    ])


def show_status():
    print('=== TIMER ===')
    subprocess.run(['systemctl', '--user', 'status', 'predictor.timer', '--no-pager'])
    print()
    print('=== SERVICE ===')
    subprocess.run(['systemctl', '--user', 'status', 'predictor.service', '--no-pager', '--lines', '20'])
    print()
    print('=== PROXIMAS EJECUCIONES ===')
    subprocess.run(['sh', '-c', 'systemctl --user list-timers --no-pager 2>&1 | grep predictor'])


def show_logs():
    subprocess.run(['journalctl', '--user', '-u', 'predictor.service', '-n', '50', '--no-pager'])


def install_timer():
    subprocess.run(['systemctl', '--user', 'daemon-reload'])
    subprocess.run(['systemctl', '--user', 'enable', 'predictor.timer'])
    subprocess.run(['systemctl', '--user', 'start', 'predictor.timer'])
    print('Timer instalado. Se ejecutara diario a las 06:00 Peru.')
    show_status()


def make_html_report(results, history):
    if not results:
        return
    generate_report(results, history)
    open_report()


def show_report():
    from report import generate as gen, open_report as open_rep
    try:
        history = load_history()
        preds = history.get('predictions', {})
        if not preds:
            print('No hay predicciones para generar reporte.')
            return
        results = []
        for p in preds.values():
            pw = p.get('predicted_winner')
            p_home = p.get('predicted_prob', 50)
            if pw and pw != p.get('home_abbr'):
                p_home = 100 - p_home
            results.append({
                'inicio': p.get('game_date', ''),
                'away_name': p.get('away_name', ''),
                'home_name': p.get('home_name', ''),
                'away_abbr': p.get('away_abbr', ''),
                'home_abbr': p.get('home_abbr', ''),
                'away_record': '',
                'home_record': '',
                'p_away': 100 - p_home,
                'p_home': p_home,
                'p_away_mkt': p.get('p_away_mkt'),
                'p_home_mkt': p.get('p_home_mkt'),
                'diff': p.get('diff'),
                'away_pitcher_name': '',
                'home_pitcher_name': '',
                'away_pitcher_era': None,
                'home_pitcher_era': None,
                'ev_home': p.get('ev_home'),
                'ev_away': p.get('ev_away'),
                'ev': p.get('ev'),
                'conf': p.get('conf', 'N/A'),
                'pick_team': p.get('predicted_winner', ''),
                'pick_prob': p.get('predicted_prob', 50),
                'venue': '',
                'completed': p.get('resolved', False),
                'in_progress': False,
                'home_score': None,
                'away_score': None,
                'actual_winner': p.get('actual_winner'),
                'status_desc': '',
                'pick_result': (p.get('actual_winner') == p.get('predicted_winner'))
                               if p.get('resolved') and p.get('actual_winner') else None,
            })
        gen(results, history)
        open_rep()
    except Exception as e:
        print(f'Error generando reporte: {e}')


def main():
    args = [a for a in sys.argv[1:] if a not in ('--simple',)]
    if args:
        cmd = args[0]
        if cmd in ('stats', '--stats'):
            show_stats()
            return
        elif cmd in ('status', '--status'):
            show_status()
            return
        elif cmd in ('logs', '--logs'):
            show_logs()
            return
        elif cmd in ('install', '--install'):
            install_timer()
            return
        elif cmd in ('report', '--report'):
            show_report()
            return
        else:
            print(f'Uso: {sys.argv[0]} [stats|status|logs|install|report]')
            sys.exit(1)

    run_prediction()


if __name__ == '__main__':
    main()
