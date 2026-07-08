import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich import box

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = f'{APP_DIR}/logs/predictor_logs.txt'

console = Console()


def display_table(results):
    has_market = any(r.get('p_home_mkt') is not None for r in results)
    has_result = any(r.get('completed') for r in results)

    table = Table(title='[bold green]MLB \u2014 Predicciones[/]',
                  box=box.SIMPLE, border_style='green', title_justify='center',
                  collapse_padding=True)
    table.add_column('Inicio\n(Peru)', style='cyan', no_wrap=True)
    table.add_column('Visitante', style='white')
    table.add_column('Nos', style='yellow', justify='right')
    if has_market:
        table.add_column('Mdo', style='magenta', justify='right')
    table.add_column('')
    table.add_column('Local', style='white')
    table.add_column('Nos', style='green', justify='right')
    if has_market:
        table.add_column('Mdo', style='magenta', justify='right')
    table.add_column('Dif', justify='right')
    table.add_column('EV', justify='right')
    table.add_column('Conf', justify='center')
    if has_result:
        table.add_column('Res', justify='center')

    for idx, r in enumerate(results):
        away_label = r['away_name']
        if r['away_record']:
            away_label += f'\n[dim]({r["away_record"]})[/]'
        if r['away_pitcher_name']:
            away_label += f'\n[dim]P: {r["away_pitcher_name"]}[/]'
            if r['away_pitcher_era'] and r['away_pitcher_era'] > 0:
                away_label += f'[dim] ({r["away_pitcher_era"]:.2f})[/]'

        home_label = r['home_name']
        if r['home_record']:
            home_label += f'\n[dim]({r["home_record"]})[/]'
        if r['home_pitcher_name']:
            home_label += f'\n[dim]P: {r["home_pitcher_name"]}[/]'
            if r['home_pitcher_era'] and r['home_pitcher_era'] > 0:
                home_label += f'[dim] ({r["home_pitcher_era"]:.2f})[/]'

        mdo_away = f'{r["p_away_mkt"]:.0f}%' if r['p_away_mkt'] else '--'
        mdo_home = f'{r["p_home_mkt"]:.0f}%' if r['p_home_mkt'] else '--'

        diff_str = ''
        if r['diff'] is not None and abs(r['diff']) > 5:
            diff_str = f'[green]+{r["diff"]:.0f}%[/]' if r['diff'] > 0 else f'[red]{r["diff"]:.0f}%[/]'

        ev_str = ''
        if r.get('ev') is not None:
            if r['ev'] > 0:
                ev_str = f'[green]+{r["ev"]:.0f}%[/]'
            else:
                ev_str = f'[red]{r["ev"]:.0f}%[/]'

        conf_str = r.get('conf', 'N/A')
        if conf_str == 'A':
            conf_str = '[green]A[/]'
        elif conf_str == 'B':
            conf_str = '[cyan]B[/]'
        elif conf_str == 'C':
            conf_str = '[yellow]C[/]'
        elif conf_str == 'D':
            conf_str = '[red]D[/]'

        if r.get('completed'):
            a, h = r['away_score'], r['home_score']
            inicio_display = f'Final\n{a}-{h}' if (a is not None and h is not None) else 'Final'
        elif r.get('in_progress'):
            inicio_display = r.get('status_desc', 'En vivo')
        else:
            inicio_display = r['inicio']

        res_str = ''
        if r.get('completed'):
            if r.get('pick_result') is True:
                res_str = '[green]\u2713[/]'
            elif r.get('pick_result') is False:
                res_str = '[red]\u2717[/]'
            else:
                res_str = '--'

        row = [inicio_display, away_label, f'{r["p_away"]:.0f}%']
        if has_market:
            row.append(mdo_away)
        row.append('@')
        row += [home_label, f'{r["p_home"]:.0f}%']
        if has_market:
            row.append(mdo_home)
        row += [diff_str, ev_str, conf_str]
        if has_result:
            row.append(res_str)
        table.add_row(*row)
        if idx < len(results) - 1:
            table.add_section()

    console.print(table)

    no_final = [r for r in results if not r.get('completed')]
    if no_final:
        sorted_preds = sorted(no_final, key=lambda r: max(r['p_home'], r['p_away']), reverse=True)
        top10 = sorted_preds[:10]
        print()
        print('Top 10 Victorias Mas Probables:')
        for i, r in enumerate(top10, 1):
            team = r['home_name'] if r['p_home'] >= r['p_away'] else r['away_name']
            opp = r['away_name'] if r['p_home'] >= r['p_away'] else r['home_name']
            prob = r['p_home'] if r['p_home'] >= r['p_away'] else r['p_away']
            ev_str = ''
            if r.get('ev') is not None:
                ev_str = f' (EV: {r["ev"]:+.0f}%)'
            estado = ' [En vivo]' if r.get('in_progress') else ''
            print(f'  {i}. {team} {prob:.0f}% vs {opp}{estado}{ev_str} [{r.get("conf", "")}]')


def write_log(results, history):
    completed = [r for r in results if r.get('completed')]
    en_vivo = [r for r in results if r.get('in_progress')]
    upcoming = [r for r in results if not r.get('completed') and not r.get('in_progress')]

    log_line = (
        f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] '
        f'{len(results)} partidos ({len(completed)} jugados) | '
        + ' | '.join(
            f'{r["home_name"] if r["p_home"] >= r["p_away"] else r["away_name"]} '
            f'{r["p_home"] if r["p_home"] >= r["p_away"] else r["p_away"]:.0f}%'
            for r in sorted((en_vivo + upcoming), key=lambda x: max(x['p_home'], x['p_away']), reverse=True)[:3]
        )
    )
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

    s = history['stats']
    if s['total'] > 0:
        print(f'\nPrecision historica: {s["correct"]}/{s["total"]} ({s["accuracy"]*100:.1f}%)')

    hoy_acertadas = sum(1 for r in completed if r.get('pick_result') is True)
    hoy_total = len(completed)
    if hoy_total > 0:
        print(f'Hoy: {hoy_acertadas}/{hoy_total} ({hoy_acertadas/hoy_total*100:.0f}%) acertados de {hoy_total} jugados')

    con_mdo = sum(1 for r in results if r.get('p_home_mkt'))
    con_ev_pos = sum(1 for r in results if r.get('ev') is not None and r['ev'] > 0)
    confs = [r.get('conf', '') for r in results if r.get('conf') not in ('', 'N/A')]
    avg_conf = ''
    if confs:
        vals = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
        avg = sum(vals.get(c, 0) for c in confs) / len(confs)
        if avg >= 3.5:
            avg_conf = 'A-'
        elif avg >= 2.5:
            avg_conf = 'B'
        elif avg >= 1.5:
            avg_conf = 'C'
        else:
            avg_conf = 'D+'
    avg_conf_str = f' ~{avg_conf}' if avg_conf else ''
    partes = [f'{len(completed)} jugados']
    if en_vivo:
        partes.append(f'{len(en_vivo)} en vivo')
    if upcoming:
        partes.append(f'{len(upcoming)} prox')
    print(f'Resumen: {len(results)} partidos ({", ".join(partes)}), {con_mdo} con mercado, {con_ev_pos} EV+, confianza media{avg_conf_str}')
