import os
import webbrowser
from datetime import datetime

APP_DIR = os.path.expanduser('~/.mlbpredictor')
REPORT_FILE = f'{APP_DIR}/report.html'


def _conf_badge(conf):
    colors = {'A': '#22c55e', 'B': '#06b6d4', 'C': '#eab308', 'D': '#ef4444', 'N/A': '#6b7280'}
    c = conf if conf in colors else 'N/A'
    return f'<span class="badge" style="background:{colors[c]}">{conf}</span>'


def _ev_str(ev):
    if ev is None:
        return '<span class="ev-none">--</span>'
    cls = 'ev-pos' if ev > 0 else 'ev-neg'
    return f'<span class="{cls}">{"+" if ev > 0 else ""}{ev:.0f}%</span>'


def _diff_str(diff):
    if diff is None or abs(diff) <= 5:
        return '<span class="ev-none">--</span>'
    cls = 'ev-pos' if diff > 0 else 'ev-neg'
    return f'<span class="{cls}">{"+" if diff > 0 else ""}{diff:.0f}%</span>'


def _pct(v):
    if v is None:
        return '--'
    return f'{v:.0f}%'


def _team_label(name, record, pitcher_name, pitcher_era):
    parts = [f'<span class="team-name">{name}</span>']
    if record:
        parts.append(f'<span class="team-record">({record})</span>')
    if pitcher_name:
        era_str = f' ({pitcher_era:.2f})' if pitcher_era and pitcher_era > 0 else ''
        parts.append(f'<span class="pitcher">P: {pitcher_name}{era_str}</span>')
    return '<div class="team-info">' + '<br>'.join(parts) + '</div>'


def _table_row(r):
    is_completed = r.get('completed')
    is_in_progress = r.get('in_progress')

    if is_completed:
        a, h = r['away_score'], r['home_score']
        fecha = r['inicio'][:5] if r['inicio'] else ''
        score_str = f'{a}-{h}' if (a is not None and h is not None) else ''
        status_str = f'{fecha}<br>Final' + (f'<br><span class="score">{score_str}</span>' if score_str else '')
    elif is_in_progress:
        status_str = f'{r["inicio"]}<br><span class="live">{r.get("status_desc", "En vivo")}</span>'
    else:
        status_str = r['inicio']

    away = _team_label(r['away_name'], r['away_record'],
                       r.get('away_pitcher_name', ''), r.get('away_pitcher_era'))
    home = _team_label(r['home_name'], r['home_record'],
                       r.get('home_pitcher_name', ''), r.get('home_pitcher_era'))

    res_str = ''
    if is_completed:
        if r.get('pick_result') is True:
            res_str = '<span class="result-ok">&#10003;</span>'
        elif r.get('pick_result') is False:
            res_str = '<span class="result-fail">&#10007;</span>'
        else:
            res_str = '<span class="ev-none">--</span>'

    row_class = 'completed' if is_completed else ('in-progress' if is_in_progress else '')

    return f'''<tr class="{row_class}">
      <td class="status-cell">{status_str}</td>
      <td>{away}</td>
      <td class="pct">{_pct(r["p_away"])}</td>
      <td class="pct mkt">{_pct(r.get("p_away_mkt"))}</td>
      <td class="vs">@</td>
      <td>{home}</td>
      <td class="pct">{_pct(r["p_home"])}</td>
      <td class="pct mkt">{_pct(r.get("p_home_mkt"))}</td>
      <td class="pct">{_diff_str(r.get("diff"))}</td>
      <td class="pct">{_ev_str(r.get("ev"))}</td>
      <td class="conf-cell">{_conf_badge(r.get("conf", "N/A"))}</td>
      <td class="result-cell">{res_str}</td>
    </tr>'''


CSS = '''* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.5; }
.header { background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); padding: 2rem 1.5rem; text-align: center; border-bottom: 2px solid #1e40af; }
.header h1 { font-size: 1.8rem; font-weight: 800; letter-spacing: -0.02em; }
.header h1 span { color: #60a5fa; }
.header .subtitle { color: #94a3b8; font-size: 0.9rem; margin-top: 0.3rem; }
.header .stats-bar { display: flex; justify-content: center; gap: 2rem; margin-top: 1rem; flex-wrap: wrap; }
.stat { text-align: center; background: rgba(255,255,255,0.05); padding: 0.5rem 1.2rem; border-radius: 10px; min-width: 100px; }
.stat .num { font-size: 1.3rem; font-weight: 700; color: #f1f5f9; }
.stat .label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.stat .num.green { color: #22c55e; }
.stat .num.yellow { color: #eab308; }
.stat .num.blue { color: #60a5fa; }
.container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
section { margin-bottom: 2rem; }
section h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.8rem; color: #f1f5f9; display: flex; align-items: center; gap: 0.5rem; }
section h2 .count { background: #1e293b; color: #94a3b8; font-size: 0.8rem; padding: 0.1rem 0.6rem; border-radius: 999px; font-weight: 600; }
.table-wrap { overflow-x: auto; border: 1px solid #1e293b; border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 0.82rem; min-width: 800px; }
thead { background: #1e293b; }
th { padding: 0.65rem 0.5rem; text-align: left; font-weight: 600; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; white-space: nowrap; }
th.center { text-align: center; }
th.right { text-align: right; }
td { padding: 0.55rem 0.5rem; border-bottom: 1px solid #1e293b; vertical-align: top; }
tr.completed { opacity: 0.75; }
tr.completed td { border-bottom-color: #334155; }
tr:last-child td { border-bottom: none; }
tr:hover { background: rgba(255,255,255,0.03); }
.vs { text-align: center; color: #475569; font-weight: 600; font-size: 0.85rem; }
.pct { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.mkt { color: #94a3b8; font-size: 0.75rem; }
.status-cell { white-space: nowrap; text-align: center; font-size: 0.75rem; }
.score { font-weight: 700; font-size: 1rem; color: #f1f5f9; }
.live { color: #f97316; font-weight: 700; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
.team-info { line-height: 1.4; }
.team-name { font-weight: 600; color: #f1f5f9; }
.team-record { color: #64748b; font-size: 0.75rem; }
.pitcher { color: #64748b; font-size: 0.72rem; }
.conf-cell { text-align: center; }
.badge { display: inline-block; font-size: 0.7rem; font-weight: 700; color: #fff; padding: 0.1rem 0.5rem; border-radius: 999px; min-width: 24px; }
.result-cell { text-align: center; font-size: 1.1rem; }
.result-ok { color: #22c55e; font-weight: 700; }
.result-fail { color: #ef4444; font-weight: 700; }
.ev-pos { color: #22c55e; }
.ev-neg { color: #ef4444; }
.ev-none { color: #475569; }
.top-picks { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.8rem; }
.pick-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1rem; }
.pick-rank { font-size: 0.75rem; color: #64748b; font-weight: 600; }
.pick-team { font-size: 1rem; font-weight: 700; margin-top: 0.2rem; color: #f1f5f9; }
.pick-detail { font-size: 0.8rem; color: #94a3b8; margin-top: 0.3rem; }
.pick-detail strong { color: #e2e8f0; }
.footer { text-align: center; padding: 1.5rem; color: #475569; font-size: 0.75rem; border-top: 1px solid #1e293b; margin-top: 2rem; }
.footer span { color: #64748b; }
'''


def generate(results, history):
    s = history.get('stats', {})
    total = s.get('total', 0)
    correct = s.get('correct', 0)
    accuracy = s.get('accuracy', 0)

    completed = [r for r in results if r.get('completed')]
    upcoming = [r for r in results if not r.get('completed')]
    hoy_acertadas = sum(1 for r in completed if r.get('pick_result') is True)
    hoy_total = len(completed)

    top = sorted(upcoming, key=lambda r: max(r['p_home'], r['p_away']), reverse=True)[:5]

    completed_rows = ''.join(_table_row(r) for r in completed)
    upcoming_rows = ''.join(_table_row(r) for r in upcoming)

    top_picks = ''
    for i, r in enumerate(top, 1):
        team = r['home_name'] if r['p_home'] >= r['p_away'] else r['away_name']
        opp = r['away_name'] if r['p_home'] >= r['p_away'] else r['home_name']
        prob = r['p_home'] if r['p_home'] >= r['p_away'] else r['p_away']
        conf = r.get('conf', '')
        ev = _ev_str(r.get('ev'))
        top_picks += f'''<div class="pick-card">
        <div class="pick-rank">#{i} &middot; {r['inicio'][:5]}</div>
        <div class="pick-team">{team}</div>
        <div class="pick-detail">vs {opp} &middot; <strong>{prob:.0f}%</strong> {_conf_badge(conf)} {ev}</div>
      </div>'''

    today_str = datetime.now().strftime('%A, %d de %B de %Y')
    months = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves',
              'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
    months_es = {'January': 'enero', 'February': 'febrero', 'March': 'marzo', 'April': 'abril',
                 'May': 'mayo', 'June': 'junio', 'July': 'julio', 'August': 'agosto',
                 'September': 'septiembre', 'October': 'octubre', 'November': 'noviembre', 'December': 'diciembre'}
    for en, es in months.items():
        today_str = today_str.replace(en, es)
    for en, es in months_es.items():
        today_str = today_str.replace(en, es)

    con_mdo = sum(1 for r in results if r.get('p_home_mkt'))
    con_ev_pos = sum(1 for r in results if r.get('ev') is not None and r['ev'] > 0)

    accuracy_str = f'{correct}/{total} ({accuracy*100:.1f}%)' if total > 0 else '--'
    hoy_str = f'{hoy_acertadas}/{hoy_total} ({hoy_acertadas/hoy_total*100:.0f}%)' if hoy_total > 0 else '--'

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLB Predictor &mdash; {datetime.now().strftime("%Y-%m-%d")}</title>
<style>{CSS}</style>
</head>
<body>
<div class="header">
  <h1><span>&#9918;</span> MLB Predictor</h1>
  <div class="subtitle">{today_str}</div>
  <div class="stats-bar">
    <div class="stat"><div class="num blue">{len(results)}</div><div class="label">Partidos hoy</div></div>
    <div class="stat"><div class="num {'' if hoy_total == 0 else ('green' if hoy_acertadas/hoy_total >= 0.5 else 'yellow')}">{hoy_str}</div><div class="label">Aciertos hoy</div></div>
    <div class="stat"><div class="num green">{accuracy_str}</div><div class="label">Hist&oacute;rico</div></div>
    <div class="stat"><div class="num">{con_mdo}</div><div class="label">Con mercado</div></div>
    <div class="stat"><div class="num">{con_ev_pos}</div><div class="label">EV+</div></div>
  </div>
</div>
<div class="container">
  <section>
    <h2>Partidos Jugados <span class="count">{hoy_total}</span></h2>
    {f'<p style="color:#64748b;font-size:0.85rem;">No hay partidos jugados a&uacute;n.</p>' if not completed else f'<div class="table-wrap"><table><thead><tr><th>Estado</th><th>Visitante</th><th class="right">Nos</th><th class="right">Mdo</th><th></th><th>Local</th><th class="right">Nos</th><th class="right">Mdo</th><th class="right">Dif</th><th class="right">EV</th><th class="center">Conf</th><th class="center">Res</th></tr></thead><tbody>{completed_rows}</tbody></table></div>'}
  </section>
  <section>
    <h2>Pr&oacute;ximos Partidos <span class="count">{len(upcoming)}</span></h2>
    {f'<p style="color:#64748b;font-size:0.85rem;">No hay partidos pr&oacute;ximos.</p>' if not upcoming else f'<div class="table-wrap"><table><thead><tr><th>Inicio</th><th>Visitante</th><th class="right">Nos</th><th class="right">Mdo</th><th></th><th>Local</th><th class="right">Nos</th><th class="right">Mdo</th><th class="right">Dif</th><th class="right">EV</th><th class="center">Conf</th><th class="center">Res</th></tr></thead><tbody>{upcoming_rows}</tbody></table></div>'}
  </section>
  <section>
    <h2>Top Picks</h2>
    {f'<p style="color:#64748b;font-size:0.85rem;">No hay partidos para mostrar.</p>' if not top_picks else f'<div class="top-picks">{top_picks}</div>'}
  </section>
</div>
<div class="footer">
  <span>Datos: ESPN API</span> &middot; <span>Modelo: Elo + Pythagorean + Forma + Descanso + Lanzador + Parque + Bullpen</span> &middot; <span>Confianza: A(&lt;3%) B(&lt;7%) C(&lt;12%) D(&gt;12%)</span>
</div>
</body>
</html>'''

    os.makedirs(APP_DIR, exist_ok=True)
    with open(REPORT_FILE, 'w') as f:
        f.write(html)
    return html


def open_report():
    webbrowser.open(f'file://{REPORT_FILE}')
    print(f'Reporte generado: {REPORT_FILE}')
