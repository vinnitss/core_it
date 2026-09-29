import pandas as pd
from datetime import date, timedelta
from modules.core.utils import engine, current_cfo, read_sql


def get_home_data():
    """Собирает все данные для стартовой страницы (с фильтром по ЦФО пользователя)."""
    today = date.today()
    year_ago = today - timedelta(days=365)

    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    cfo_and_c = "AND c.цфо = %(user_cfo)s" if cfo else ""
    cfo_and_d = "AND d.цфо = %(user_cfo)s" if cfo else ""
    params_global = {'user_cfo': cfo} if cfo else {}

    # -------- KPI --------
    try:
        kz_total = float(read_sql(f"""
            SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
            WHERE вид_задолженности = 'Кредиторская' {cfo_and}
        """, engine, params=params_global).iloc[0, 0])
    except Exception:
        kz_total = 0.0

    try:
        dz_total = float(read_sql(f"""
            SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
            WHERE вид_задолженности = 'Дебиторская' {cfo_and}
        """, engine, params=params_global).iloc[0, 0])
    except Exception:
        dz_total = 0.0

    unpaid_total = float(read_sql(f"""
        SELECT COALESCE(SUM(сумма_заявки),0)
        FROM applications
        WHERE оплачена = 'Нет'
          AND статус_согласования IS NOT NULL
          AND статус_согласования != ''
          AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')
          {cfo_and}
    """, engine, params=params_global).iloc[0, 0])

    active_contracts = int(read_sql(f"""
        SELECT COUNT(DISTINCT c.id)
        FROM contracts c
        JOIN application_contracts ac ON ac.contract_id = c.id
        JOIN applications a 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.дата >= %(year_ago)s
          AND (a.состояние_заявки IS NULL OR a.состояние_заявки != 'Аннулирован')
          {cfo_and_c}
    """, engine, params={**params_global, 'year_ago': year_ago}).iloc[0, 0])

    # -------- Требует внимания --------
    try:
        from modules.dashboard.services import get_dashboard_data
        dash = get_dashboard_data()
        expiring_count = len(dash['expiring'])
        limit_count = len(dash['limit_exceeded'])
        no_end_count = len(dash['no_end_date'])
    except Exception:
        expiring_count = limit_count = no_end_count = 0

    try:
        diff_count = int(read_sql(f"""
            WITH kz AS (
                SELECT d.договор_код, SUM(d.сумма_остаток) AS kz_sum
                FROM debts d
                WHERE d.вид_задолженности = 'Кредиторская'
                  {cfo_and_d}
                GROUP BY d.договор_код
            ),
            apps AS (
                SELECT c.external_code AS code, SUM(a.сумма_заявки) AS apps_sum
                FROM applications a
                JOIN application_contracts ac 
                    ON a.номер_заявки = ac.application_number 
                   AND a.дата = ac.application_date
                JOIN contracts c ON c.id = ac.contract_id
                WHERE a.оплачена = 'Нет' 
                  AND a.статус_согласования IS NOT NULL 
                  AND a.статус_согласования != ''
                  AND (a.состояние_заявки IS NULL OR a.состояние_заявки != 'Аннулирован')
                  {cfo_and_c}
                GROUP BY c.external_code
            )
            SELECT COUNT(*)
            FROM kz
            FULL OUTER JOIN apps ON kz.договор_код = apps.code
            WHERE ABS(COALESCE(kz.kz_sum,0) - COALESCE(apps.apps_sum,0)) > 1
        """, engine, params=params_global).iloc[0, 0])
    except Exception:
        diff_count = 0

    # -------- Прогноз исчерпания лимитов --------
    try:
        from modules.dashboard.services import get_limits_forecast
        forecast = get_limits_forecast(days_horizon=60)
        forecast_critical_count = sum(1 for f in forecast if f['is_critical'])
    except Exception:
        forecast_critical_count = 0

    # -------- Дата актуальности (не фильтруется по ЦФО) --------
    try:
        imported_at = read_sql("SELECT MAX(imported_at) FROM debts", engine).iloc[0, 0]
        if pd.isna(imported_at):
            imported_at = None
    except Exception:
        imported_at = None

    return {
        'kz_total': kz_total,
        'dz_total': dz_total,
        'unpaid_total': unpaid_total,
        'active_contracts': active_contracts,
        'expiring_count': expiring_count,
        'limit_count': limit_count,
        'no_end_count': no_end_count,
        'diff_count': diff_count,
        'forecast_critical_count': forecast_critical_count,
        'imported_at': imported_at,
        'today': today,
    }