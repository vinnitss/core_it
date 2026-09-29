"""
Реестр виджетов для персонального дашборда.
Каждый виджет — функция, возвращающая данные для рендера.
"""
import logging
from datetime import date, timedelta

import pandas as pd

from modules.core.utils import engine, current_cfo, read_sql

logger = logging.getLogger(__name__)


# ==================== РЕЕСТР ВИДЖЕТОВ ====================
WIDGETS = {
    # --- KPI ---
    'kpi_kz': {
        'name': 'Кредиторская задолженность',
        'category': 'Задолженность',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_kz',
    },
    'kpi_apps': {
        'name': 'Неоплаченные заявки',
        'category': 'Заявки',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_unpaid_apps',
    },
    'kpi_expiring': {
        'name': 'Истекающие договоры',
        'category': 'Договоры',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_expiring',
    },
    'kpi_mismatch': {
        'name': 'Расхождения КЗ и заявок',
        'category': 'Задолженность',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_mismatch',
    },
    'kpi_dead': {
        'name': 'Мёртвые договоры',
        'category': 'Договоры',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_dead',
    },
    'kpi_active_contracts': {
        'name': 'Активные договоры',
        'category': 'Договоры',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_active_contracts',
    },
        'kpi_registers_approval': {
        'name': 'Реестры на согласовании',
        'category': 'Реестры',
        'type': 'kpi',
        'default_size': 'small',
        'renderer': 'widgets/kpi.html',
        'service': 'get_kpi_registers_approval',
    },

    # --- Таблицы ---
    'table_reconciliation': {
        'name': 'Сверка по договорам',
        'category': 'Задолженность',
        'type': 'table',
        'default_size': 'full',
        'renderer': 'widgets/table.html',
        'service': 'get_table_reconciliation',
    },
    'table_top_contractors': {
        'name': 'Топ-10 контрагентов',
        'category': 'Заявки',
        'type': 'table',
        'default_size': 'medium',
        'renderer': 'widgets/table.html',
        'service': 'get_table_top_contractors',
    },
    'table_stuck': {
        'name': 'Зависшие заявки',
        'category': 'Операции',
        'type': 'table',
        'default_size': 'full',
        'renderer': 'widgets/table.html',
        'service': 'get_table_stuck',
    },
    'table_registers_cfo': {
        'name': 'Реестры по ЦФО',
        'category': 'Реестры',
        'type': 'table',
        'default_size': 'full',
        'renderer': 'widgets/table.html',
        'service': 'get_table_registers_cfo',
    },

    # --- Графики ---
    'chart_payments': {
        'name': 'Динамика оплат',
        'category': 'Заявки',
        'type': 'chart',
        'default_size': 'full',
        'renderer': 'widgets/chart.html',
        'service': 'get_chart_payments',
    },
    'chart_monthly': {
        'name': 'Заявки по месяцам',
        'category': 'Заявки',
        'type': 'chart',
        'default_size': 'full',
        'renderer': 'widgets/chart.html',
        'service': 'get_chart_monthly',
    },
}


# ==================== СЕРВИСЫ ВИДЖЕТОВ ====================

def get_kpi_kz(params=None):
    cfo = current_cfo()
    where = "вид_задолженности = 'Кредиторская'"
    sql_params = {}
    if cfo:
        where += " AND цфо = %(cfo)s"
        sql_params['cfo'] = cfo
    value = read_sql(f"""
        SELECT COALESCE(SUM(сумма_остаток), 0) AS s FROM debts WHERE {where}
    """, engine, params=sql_params).iloc[0]['s']
    return {
        'value': float(value),
        'format': 'money',
        'label': 'Кредиторская задолженность',
        'color': 'danger',
        'icon': 'fa-file-invoice-dollar',
        'link': '/contracts/',
    }


def get_kpi_unpaid_apps(params=None):
    cfo = current_cfo()
    where = """оплачена = 'Нет'
               AND статус_согласования IS NOT NULL
               AND статус_согласования != ''
               AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')"""
    sql_params = {}
    if cfo:
        where += " AND цфо = %(cfo)s"
        sql_params['cfo'] = cfo
    value = read_sql(f"""
        SELECT COALESCE(SUM(сумма_заявки), 0) AS s FROM applications WHERE {where}
    """, engine, params=sql_params).iloc[0]['s']
    return {
        'value': float(value),
        'format': 'money',
        'label': 'Неоплаченные заявки',
        'color': 'warning',
        'icon': 'fa-hourglass-half',
        'link': '/reports/',
    }


def get_kpi_expiring(params=None):
    from modules.dashboard.services import get_dashboard_data
    try:
        dash = get_dashboard_data()
        value = len(dash['expiring'])
    except Exception:
        value = 0
    return {
        'value': value,
        'format': 'int',
        'label': 'Истекающие договоры',
        'color': 'warning',
        'icon': 'fa-clock',
        'link': '/dashboard/portfolio',
    }


def get_kpi_mismatch(params=None):
    cfo = current_cfo()
    cfo_and_d = "AND d.цфо = %(cfo)s" if cfo else ""
    cfo_and_c = "AND c.цфо = %(cfo)s" if cfo else ""
    sql_params = {'cfo': cfo} if cfo else {}

    value = read_sql(f"""
        WITH kz AS (
            SELECT d.договор_код, SUM(d.сумма_остаток) AS kz_sum
            FROM debts d
            WHERE d.вид_задолженности = 'Кредиторская' {cfo_and_d}
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
        SELECT COUNT(*) AS c
        FROM kz FULL OUTER JOIN apps ON kz.договор_код = apps.code
        WHERE ABS(COALESCE(kz.kz_sum, 0) - COALESCE(apps.apps_sum, 0)) > 1
    """, engine, params=sql_params).iloc[0]['c']
    return {
        'value': int(value),
        'format': 'int',
        'label': 'Расхождения КЗ и заявок',
        'color': 'danger',
        'icon': 'fa-balance-scale',
        'link': '/dashboard/portfolio',
    }


def get_kpi_dead(params=None):
    from modules.dashboard.services import get_contracts_portfolio
    try:
        data = get_contracts_portfolio()
        value = len(data['dead'])
    except Exception:
        value = 0
    return {
        'value': value,
        'format': 'int',
        'label': 'Мёртвые договоры',
        'color': 'secondary',
        'icon': 'fa-bed',
        'link': '/dashboard/portfolio',
    }


def get_kpi_active_contracts(params=None):
    today = date.today()
    year_ago = today - timedelta(days=365)
    cfo = current_cfo()
    cfo_and = "AND c.цфо = %(cfo)s" if cfo else ""
    sql_params = {'year_ago': year_ago}
    if cfo:
        sql_params['cfo'] = cfo
    value = read_sql(f"""
        SELECT COUNT(DISTINCT c.id) AS c
        FROM contracts c
        JOIN application_contracts ac ON ac.contract_id = c.id
        JOIN applications a 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.дата >= %(year_ago)s
          AND (a.состояние_заявки IS NULL OR a.состояние_заявки != 'Аннулирован')
          {cfo_and}
    """, engine, params=sql_params).iloc[0]['c']
    return {
        'value': int(value),
        'format': 'int',
        'label': 'Активные договоры',
        'color': 'success',
        'icon': 'fa-file-contract',
        'link': '/contracts/',
    }


def get_kpi_registers_approval(params=None):
    """
    KPI: количество реестров со статусом «На согласовании».
    Для не-админов — только реестры, у которых есть хотя бы одна
    связанная заявка из ЦФО пользователя.
    """
    cfo = current_cfo()

    if cfo:
        query = """
            SELECT COUNT(DISTINCT r.номер_реестра) AS c
            FROM v_registers r
            WHERE r.вычисленный_статус ILIKE 'На согласовании%%'
              AND EXISTS (
                  SELECT 1 FROM applications a
                  WHERE a.номер_рп = r.номер_реестра
                    AND a.цфо = %(cfo)s
              )
        """
        value = read_sql(query, engine, params={'cfo': cfo}).iloc[0]['c']
    else:
        query = """
            SELECT COUNT(*) AS c
            FROM v_registers r
            WHERE r.вычисленный_статус ILIKE 'На согласовании%%'
        """
        value = read_sql(query, engine).iloc[0]['c']

    return {
        'value': int(value),
        'format': 'int',
        'label': 'Реестры на согласовании',
        'color': 'primary',
        'icon': 'fa-clipboard-list',
        'link': '/dashboard/my',
    }


def get_table_registers_cfo(params=None):
    """
    Таблица реестров по ЦФО пользователя.
    Колонки: ИСД, Номер РП, Дата, Контрагент, Количество заявок.
    Выпадающий фильтр — по статусу (поле filter_column).
    """
    cfo = current_cfo()

    # Формируем WHERE для ЦФО
    if cfo:
        cfo_filter = "AND a.цфо = %(cfo)s"
        sql_params = {'cfo': cfo}
    else:
        cfo_filter = ""
        sql_params = {}

    query = f"""
        WITH filtered AS (
            SELECT 
                r.номер_реестра,
                r.дата_реестра,
                r.вычисленный_статус,
                a.стг_подсказка_исд,
                a.контрагент,
                a.номер_заявки
            FROM v_registers r
            JOIN applications a 
                ON a.номер_рп = r.номер_реестра
            WHERE 1=1
              {cfo_filter}
        )
        SELECT 
            номер_реестра,
            MIN(дата_реестра) AS дата_реестра,
            MAX(вычисленный_статус) AS вычисленный_статус,
            STRING_AGG(DISTINCT стг_подсказка_исд, '; ' ORDER BY стг_подсказка_исд) 
                FILTER (WHERE стг_подсказка_исд IS NOT NULL AND стг_подсказка_исд != '') AS исд,
            MODE() WITHIN GROUP (ORDER BY контрагент) AS контрагент,
            COUNT(DISTINCT номер_заявки) AS apps_count
        FROM filtered
        GROUP BY номер_реестра
        ORDER BY дата_реестра DESC NULLS LAST
        LIMIT 500
    """
    df = read_sql(query, engine, params=sql_params)

    # Преобразуем дату в строку
    if 'дата_реестра' in df.columns:
        df['дата_реестра'] = df['дата_реестра'].apply(
            lambda d: d.strftime('%d.%m.%Y') if pd.notna(d) else ''
        )

    rows = df.to_dict('records')

    return {
        'columns': [
            {'key': 'исд', 'label': 'ИСД'},
            {'key': 'номер_реестра', 'label': 'Номер РП'},
            {'key': 'дата_реестра', 'label': 'Дата'},
            {'key': 'контрагент', 'label': 'Контрагент'},
            {'key': 'apps_count', 'label': 'Заявок', 'format': 'int'},
        ],
        'rows': rows,
        'filter_column': 'вычисленный_статус',
        'filter_label': 'Статус',
        'empty': 'Нет реестров по вашему ЦФО',
        'link_all': '/dashboard/my',
    }


def get_table_reconciliation(params=None):
    """Упрощённая сверка — топ-20 расхождений."""
    from modules.dashboard.services import get_contracts_portfolio
    try:
        data = get_contracts_portfolio()
        rows = data['mismatched'][:20]
    except Exception:
        rows = []
    return {
        'columns': [
            {'key': 'contract_code', 'label': 'Код договора'},
            {'key': 'counterparty', 'label': 'Контрагент'},
            {'key': 'kz_sum', 'label': 'КЗ', 'format': 'money'},
            {'key': 'apps_sum', 'label': 'Заявки', 'format': 'money'},
            {'key': 'diff', 'label': 'Расхождение', 'format': 'money', 'color_by_sign': True},
        ],
        'rows': rows,
        'empty': 'Нет расхождений',
        'link_all': '/dashboard/portfolio',
    }


def get_table_top_contractors(params=None):
    cfo = current_cfo()
    where = "1=1"
    sql_params = {}
    if cfo:
        where += " AND цфо = %(cfo)s"
        sql_params['cfo'] = cfo
    df = read_sql(f"""
        SELECT контрагент, COUNT(*) AS cnt, SUM(сумма_заявки) AS total
        FROM applications
        WHERE {where}
          AND период_услуги >= NOW() - INTERVAL '12 months'
          AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')
        GROUP BY контрагент
        ORDER BY total DESC
        LIMIT 10
    """, engine, params=sql_params)
    rows = df.to_dict('records')
    return {
        'columns': [
            {'key': 'контрагент', 'label': 'Контрагент'},
            {'key': 'cnt', 'label': 'Заявок', 'format': 'int'},
            {'key': 'total', 'label': 'Сумма', 'format': 'money'},
        ],
        'rows': rows,
        'empty': 'Нет данных',
        'link_all': '/dashboard/spending',
    }


def get_table_stuck(params=None):
    from modules.dashboard.services import get_operations_dashboard_data
    try:
        data = get_operations_dashboard_data()
        rows = data['stuck'][:10]
    except Exception:
        rows = []
    return {
        'columns': [
            {'key': 'номер_заявки', 'label': '№ заявки'},
            {'key': 'контрагент', 'label': 'Контрагент'},
            {'key': 'сумма_заявки', 'label': 'Сумма', 'format': 'money'},
            {'key': 'статус_согласования', 'label': 'Статус'},
            {'key': 'days_in_status', 'label': 'Дней в статусе', 'format': 'int', 'color_by_value': True},
        ],
        'rows': rows,
        'empty': 'Нет зависших заявок',
        'link_all': '/dashboard/operations',
    }


def get_chart_payments(params=None):
    from modules.dashboard.services import get_payments_dynamics
    data = get_payments_dynamics('year')
    return {
        'type': 'bar',
        'labels': [r['period_label'] for r in data],
        'datasets': [
            {
                'label': 'Сумма',
                'data': [r['total'] for r in data],
                'color': 'rgba(54, 162, 235, 0.6)',
            },
        ],
        'empty': 'Нет данных',
        'link_all': '/dashboard/payments',
    }


def get_chart_monthly(params=None):
    cfo = current_cfo()
    where = "1=1"
    sql_params = {}
    if cfo:
        where += " AND цфо = %(cfo)s"
        sql_params['cfo'] = cfo
    df = read_sql(f"""
        SELECT to_char(дата, 'YYYY-MM') AS month,
               COUNT(*) AS cnt,
               SUM(сумма_заявки) AS total
        FROM applications
        WHERE {where}
          AND дата >= NOW() - INTERVAL '12 months'
          AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')
        GROUP BY month
        ORDER BY month
    """, engine, params=sql_params)
    data = df.to_dict('records')
    return {
        'type': 'bar',
        'labels': [r['month'] for r in data],
        'datasets': [
            {
                'label': 'Сумма',
                'data': [float(r['total'] or 0) for r in data],
                'color': 'rgba(54, 162, 235, 0.6)',
                'yAxisID': 'y',
            },
            {
                'label': 'Заявок',
                'data': [int(r['cnt']) for r in data],
                'color': 'rgba(255, 99, 132, 0.8)',
                'type': 'line',
                'yAxisID': 'y1',
            },
        ],
        'empty': 'Нет данных',
        'link_all': '/dashboard/finance',
    }


def render_widget(widget_key, params=None):
    """Возвращает данные виджета, вызвав его сервис."""
    if widget_key not in WIDGETS:
        return None
    meta = WIDGETS[widget_key]
    service_name = meta['service']
    fn = globals().get(service_name)
    if not fn:
        return None
    try:
        return fn(params)
    except Exception as e:
        logger.warning(f"Widget {widget_key} error: {e}")
        return {'error': str(e)[:200], 'empty': 'Ошибка загрузки'}