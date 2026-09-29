from datetime import date, timedelta
import pandas as pd
from modules.core.utils import engine, current_cfo, read_sql

# ==================== ОБЩИЕ ХЕЛПЕРЫ ====================
def _period_range(period):
    """Возвращает (start_date, end_date) для календарного периода."""
    today = date.today()
    if period == 'month':
        return today.replace(day=1), today
    elif period == 'quarter':
        q = (today.month - 1) // 3
        return date(today.year, q * 3 + 1, 1), today
    elif period == 'year':
        return date(today.year, 1, 1), today
    return None, None


def _build_common_where(filters, params):
    """
    Общие условия: без аннулированных, с фильтрами
    по ЦФО пользователя / периоду / проекту / контрагенту.
    """
    where = ["(a.состояние_заявки IS NULL OR a.состояние_заявки != 'Аннулирован')"]

    # Фильтр по ЦФО пользователя
    cfo = current_cfo()
    if cfo:
        where.append("a.цфо = %(user_cfo)s")
        params['user_cfo'] = cfo

    if filters.get('проект'):
        where.append("a.проект = %(проект)s")
        params['проект'] = filters['проект']
    if filters.get('контрагент'):
        where.append("a.контрагент ILIKE %(контрагент)s")
        params['контрагент'] = f"%{filters['контрагент']}%"
    if filters.get('period') and filters['period'] != 'all':
        start, end = _period_range(filters['period'])
        if start:
            where.append("a.дата >= %(date_from)s")
            params['date_from'] = start
        where.append("a.дата <= %(date_to)s")
        params['date_to'] = end
    return "WHERE " + " AND ".join(where)


# ==================== ГЛАВНЫЙ ДАШБОРД ДОГОВОРОВ (плитки) ====================
def get_dashboard_data():
    """
    Возвращает списки договоров по категориям:
      - expiring (истекающий срок)
      - limit_exceeded (исчерпан лимит)
      - no_end_date (без срока)
    Учитывает условия пролонгации и ЦФО пользователя.
    """
    today = date.today()
    year_ago = today - timedelta(days=365)
    cfo = current_cfo()

    PROLONGATION_VALUES = {
        'автоматически на год',
        'автоматически на неопределенный срок',
        'автоматически на неопределённый срок',
        'допускает продление',
    }

    cfo_and = "AND c.цфо = %(user_cfo)s" if cfo else ""
    params = {'year_ago': year_ago}
    if cfo:
        params['user_cfo'] = cfo

    query = f"""
    SELECT
        c.id,
        c.contract_number,
        c.counterparty,
        c.amount,
        c.start_date,
        c.end_date,
        c.status,
        c.условия_пролонгации,
        COALESCE(SUM(a.сумма_заявки) FILTER (
            WHERE a.статус_согласования IS NOT NULL
              AND a.статус_согласования != ''
              AND (a.состояние_заявки IS NULL
                   OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        ), 0) as spent,
        MAX(a.дата) as last_application_date
    FROM contracts c
    LEFT JOIN application_contracts ac ON ac.contract_id = c.id
    LEFT JOIN applications a ON a.номер_заявки = ac.application_number AND a.дата = ac.application_date
    WHERE 1=1 {cfo_and}
    GROUP BY c.id
    HAVING MAX(a.дата) >= %(year_ago)s OR MAX(a.дата) IS NULL
    ORDER BY c.end_date NULLS LAST, c.counterparty;
    """
    df = read_sql(query, engine, params=params)

    expiring = []
    limit_exceeded = []
    no_end_date = []

    for _, row in df.iterrows():
        prolongation_raw = str(row['условия_пролонгации'] or '').strip().lower().rstrip('.')
        has_prolongation = prolongation_raw in PROLONGATION_VALUES

        has_end_date = pd.notna(row['end_date'])

        contract_info = {
            'contract_number': row['contract_number'] or str(row['id']),
            'counterparty': row['counterparty'],
            'amount': row['amount'],
            'spent': row['spent'],
            'end_date': row['end_date'],
        }

        amount = float(row['amount']) if row['amount'] is not None else 0.0
        spent  = float(row['spent'])  if row['spent']  is not None else 0.0
        if amount > 0 and spent >= 0.9 * amount:
            limit_exceeded.append(contract_info)

        if (not has_prolongation) and has_end_date and (row['end_date'] - today).days <= 30:
            expiring.append(contract_info)

        if not has_end_date:
            no_end_date.append(contract_info)

    return {
        'expiring': expiring,
        'limit_exceeded': limit_exceeded,
        'no_end_date': no_end_date,
        'total_active': len(df),
    }


def get_all_contracts_data():
    """Все договоры для экспорта (с фильтром по ЦФО)."""
    today = date.today()
    cfo = current_cfo()
    cfo_and = "AND c.цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    query = f"""
    SELECT
        c.id,
        c.contract_number,
        c.counterparty,
        c.inn,
        c.amount,
        c.start_date,
        c.end_date,
        c.status,
        c.ответственный,
        c.цфо,
        c.условия_пролонгации,
        COALESCE(SUM(a.сумма_заявки) FILTER (
            WHERE a.статус_согласования IS NOT NULL
              AND a.статус_согласования != ''
              AND (a.состояние_заявки IS NULL
                   OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        ), 0) as spent,
        MAX(a.дата) as last_application_date
    FROM contracts c
    LEFT JOIN application_contracts ac ON ac.contract_id = c.id
    LEFT JOIN applications a ON a.номер_заявки = ac.application_number AND a.дата = ac.application_date
    WHERE 1=1 {cfo_and}
    GROUP BY c.id
    ORDER BY c.counterparty;
    """
    df = read_sql(query, engine, params=params)
    df['остаток'] = df['amount'] - df['spent']
    df['активен'] = df['last_application_date'].apply(
        lambda d: 'Да' if pd.notna(d) and d >= today - timedelta(days=365) else 'Нет'
    )
    return df


# ==================== ДИНАМИКА ОПЛАТ ====================
def get_payments_dynamics(period='year'):
    """
    Динамика оплат с фильтром периода и ЦФО.
    period: 'week' | 'month' | 'quarter' | 'year' | 'all'
    """
    today = date.today()
    cfo = current_cfo()

    if period == 'week':
        date_from = today - timedelta(days=6)
        trunc = "DATE_TRUNC('day', дата_оплаты_фактич)"
        fmt = '%d.%m'
    elif period == 'month':
        date_from = today - timedelta(days=29)
        trunc = "DATE_TRUNC('day', дата_оплаты_фактич)"
        fmt = '%d.%m'
    elif period == 'quarter':
        date_from = today - timedelta(days=89)
        trunc = "DATE_TRUNC('week', дата_оплаты_фактич)"
        fmt = 'нед. %W %Y'
    elif period == 'all':
        date_from = None
        trunc = "DATE_TRUNC('month', дата_оплаты_фактич)"
        fmt = '%m.%Y'
    else:  # year
        date_from = today - timedelta(days=364)
        trunc = "DATE_TRUNC('month', дата_оплаты_фактич)"
        fmt = '%m.%Y'

    where = [
        "дата_оплаты_фактич IS NOT NULL",
        "(состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')",
    ]
    params = {}
    if cfo:
        where.append("цфо = %(user_cfo)s")
        params['user_cfo'] = cfo
    if date_from:
        where.append("дата_оплаты_фактич >= %(date_from)s")
        params['date_from'] = date_from

    where_sql = "WHERE " + " AND ".join(where)

    query = f"""
    SELECT 
        {trunc} AS period,
        COUNT(*) AS cnt,
        COALESCE(SUM(сумма_заявки), 0) AS total
    FROM applications
    {where_sql}
    GROUP BY period
    ORDER BY period
    """
    df = read_sql(query, engine, params=params)

    def format_period(d):
        if pd.isna(d):
            return ''
        return d.strftime(fmt)

    df['period_label'] = df['period'].apply(format_period)
    return df.to_dict('records')


# ==================== ФИНАНСОВЫЙ ДАШБОРД ====================
def get_finance_filter_options():
    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    projects = read_sql(f"""
        SELECT DISTINCT проект FROM applications
        WHERE проект IS NOT NULL AND проект != ''
          {cfo_and}
        ORDER BY проект
    """, engine, params=params)['проект'].tolist()
    return {'projects': projects}


def get_finance_dashboard_data(filters=None):
    filters = filters or {}
    params = {}
    where_sql = _build_common_where(filters, params)

    kpi_row = read_sql(f"""
        SELECT
            COUNT(*) AS cnt,
            COALESCE(SUM(сумма_заявки), 0) AS total_sum,
            COALESCE(SUM(CASE WHEN оплачена = 'Да' THEN сумма_заявки ELSE 0 END), 0) AS paid_sum,
            COALESCE(SUM(CASE WHEN оплачена = 'Нет' THEN сумма_заявки ELSE 0 END), 0) AS unpaid_sum
        FROM applications a
        {where_sql}
    """, engine, params=params).iloc[0]

    total_count = int(kpi_row['cnt'])
    total_sum = float(kpi_row['total_sum'])
    kpi = {
        'total_count': total_count,
        'total_sum': total_sum,
        'paid_sum': float(kpi_row['paid_sum']),
        'unpaid_sum': float(kpi_row['unpaid_sum']),
        'avg_check': total_sum / total_count if total_count > 0 else 0.0,
        'paid_pct': (float(kpi_row['paid_sum']) / total_sum * 100) if total_sum > 0 else 0.0,
    }

    monthly = read_sql(f"""
        SELECT to_char(a.дата, 'YYYY-MM') AS month,
               COUNT(*) AS cnt,
               COALESCE(SUM(a.сумма_заявки), 0) AS total
        FROM applications a
        {where_sql}
        GROUP BY month
        ORDER BY month
    """, engine, params=params).to_dict('records')

    top_cp = read_sql(f"""
        SELECT a.контрагент, COUNT(*) AS cnt, SUM(a.сумма_заявки) AS total
        FROM applications a
        {where_sql}
        GROUP BY a.контрагент
        ORDER BY total DESC
        LIMIT 10
    """, engine, params=params).to_dict('records')

    top_proj = read_sql(f"""
        SELECT a.проект, COUNT(*) AS cnt, SUM(a.сумма_заявки) AS total
        FROM applications a
        {where_sql}
        GROUP BY a.проект
        ORDER BY total DESC
        LIMIT 10
    """, engine, params=params).to_dict('records')

    statuses = read_sql(f"""
        SELECT COALESCE(a.статус_согласования, '(не указан)') AS status,
               COUNT(*) AS cnt,
               SUM(a.сумма_заявки) AS total
        FROM applications a
        {where_sql}
        GROUP BY status
        ORDER BY total DESC
    """, engine, params=params).to_dict('records')

    return {
        'kpi': kpi,
        'monthly': monthly,
        'top_counterparties': top_cp,
        'top_projects': top_proj,
        'statuses': statuses,
    }


# ==================== ОПЕРАЦИОННЫЙ ДАШБОРД ====================
def get_operations_filter_options():
    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    projects = read_sql(f"""
        SELECT DISTINCT проект FROM applications
        WHERE проект IS NOT NULL AND проект != ''
          {cfo_and}
        ORDER BY проект
    """, engine, params=params)['проект'].tolist()
    return {'projects': projects}


def get_operations_dashboard_data(filters=None):
    """
    Операционный дашборд.
    Все метрики — «состояние на сейчас».
    Период применяется только к графику динамики поступления.
    Данные фильтруются по ЦФО пользователя.
    """
    filters = filters or {}
    params = {}
    cfo = current_cfo()

    base_where = [
        "(a.состояние_заявки IS NULL OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))",
        "a.оплачена = 'Нет'",
    ]
    if cfo:
        base_where.append("a.цфо = %(user_cfo)s")
        params['user_cfo'] = cfo
    if filters.get('проект'):
        base_where.append("a.проект = %(проект)s")
        params['проект'] = filters['проект']
    if filters.get('контрагент'):
        base_where.append("a.контрагент ILIKE %(контрагент)s")
        params['контрагент'] = f"%{filters['контрагент']}%"

    where_in_work = "WHERE " + " AND ".join(base_where)

    monthly_where = list(base_where)
    monthly_params = dict(params)
    if filters.get('period') and filters['period'] != 'all':
        start, end = _period_range(filters['period'])
        if start:
            monthly_where.append("a.дата >= %(date_from)s")
            monthly_params['date_from'] = start
        monthly_where.append("a.дата <= %(date_to)s")
        monthly_params['date_to'] = end
    where_monthly = "WHERE " + " AND ".join(monthly_where)

    kpi_row = read_sql(f"""
        SELECT COUNT(*) AS cnt, COALESCE(SUM(сумма_заявки), 0) AS total
        FROM applications a
        {where_in_work}
    """, engine, params=params).iloc[0]

    overdue_params = dict(params)
    overdue_params['status_pattern'] = 'На согласовании%'
    overdue_count = int(read_sql(f"""
        SELECT COUNT(*) AS cnt
        FROM applications a
        {where_in_work}
          AND a.статус_согласования ILIKE %(status_pattern)s
          AND a.дата_последнего_статуса IS NOT NULL
          AND a.дата_последнего_статуса < NOW() - INTERVAL '30 days'
    """, engine, params=overdue_params).iloc[0]['cnt'])

    avg_row = read_sql(f"""
        SELECT AVG(EXTRACT(EPOCH FROM (NOW() - a.дата::timestamp)) / 86400) AS avg_days
        FROM applications a
        {where_in_work}
    """, engine, params=params).iloc[0]
    avg_days = float(avg_row['avg_days']) if avg_row['avg_days'] is not None else 0.0

    top_resp_df = read_sql(f"""
        SELECT a.ответственный, COUNT(*) AS cnt
        FROM applications a
        {where_in_work}
          AND a.ответственный IS NOT NULL AND a.ответственный != ''
        GROUP BY a.ответственный
        ORDER BY cnt DESC
        LIMIT 1
    """, engine, params=params)
    top_responsible = top_resp_df.iloc[0].to_dict() if not top_resp_df.empty else None

    kpi = {
        'in_work_count': int(kpi_row['cnt']),
        'in_work_sum': float(kpi_row['total']),
        'overdue_count': overdue_count,
        'avg_days': round(avg_days, 1),
        'top_responsible': top_responsible,
    }

    funnel = read_sql(f"""
        SELECT COALESCE(a.статус_согласования, '(не указан)') AS status,
               COUNT(*) AS cnt,
               SUM(a.сумма_заявки) AS total
        FROM applications a
        {where_in_work}
        GROUP BY status
        ORDER BY cnt DESC
    """, engine, params=params).to_dict('records')

    monthly = read_sql(f"""
        SELECT to_char(a.дата, 'YYYY-MM') AS month,
               COUNT(*) AS cnt,
               COALESCE(SUM(a.сумма_заявки), 0) AS total
        FROM applications a
        {where_monthly}
        GROUP BY month
        ORDER BY month
    """, engine, params=monthly_params).to_dict('records')

    stuck = read_sql(f"""
        SELECT a.номер_заявки, a.дата, a.контрагент, a.сумма_заявки,
               a.статус_согласования, a.ответственный,
               EXTRACT(EPOCH FROM (NOW() - a.дата_последнего_статуса::timestamp)) / 86400 AS days_in_status
        FROM applications a
        {where_in_work}
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования NOT ILIKE 'Согласовано%%'
          AND a.дата_последнего_статуса IS NOT NULL
        ORDER BY days_in_status DESC NULLS LAST
        LIMIT 10
    """, engine, params=params)
    stuck_records = stuck.to_dict('records')
    for r in stuck_records:
        if r.get('days_in_status') is not None:
            r['days_in_status'] = int(float(r['days_in_status']))

    workload = read_sql(f"""
        SELECT a.ответственный,
               COUNT(*) AS cnt,
               SUM(a.сумма_заявки) AS total,
               AVG(EXTRACT(EPOCH FROM (NOW() - a.дата::timestamp)) / 86400) AS avg_age_days
        FROM applications a
        {where_in_work}
          AND a.ответственный IS NOT NULL AND a.ответственный != ''
        GROUP BY a.ответственный
        ORDER BY cnt DESC
        LIMIT 20
    """, engine, params=params).to_dict('records')
    for r in workload:
        if r.get('avg_age_days') is not None:
            r['avg_age_days'] = int(float(r['avg_age_days']))

    return {
        'kpi': kpi,
        'funnel': funnel,
        'monthly': monthly,
        'stuck': stuck_records,
        'workload': workload,
    }


# ==================== ДАШБОРД ДОГОВОРОВ (таблица) ====================
def get_contracts_filter_options():
    """Список ответственных для фильтра (с учётом ЦФО)."""
    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    responsibles = read_sql(f"""
        SELECT DISTINCT ответственный FROM contracts
        WHERE ответственный IS NOT NULL AND ответственный != ''
          {cfo_and}
        ORDER BY ответственный
    """, engine, params=params)['ответственный'].tolist()
    return {'responsibles': responsibles}


PROLONGATION_VALUES = {
    'автоматически на год',
    'автоматически на неопределенный срок',
    'автоматически на неопределённый срок',
    'допускает продление',
}


def get_contracts_dashboard_data(filters=None):
    """
    Таблица всех договоров с подсветкой проблем и прогнозом исчерпания.
    Фильтры: ответственный, flags, ЦФО пользователя.
    """
    filters = filters or {}
    where_clauses = []
    params = {}

    cfo = current_cfo()
    if cfo:
        where_clauses.append("c.цфо = %(user_cfo)s")
        params['user_cfo'] = cfo

    if filters.get('ответственный'):
        where_clauses.append("c.ответственный = %(ответственный)s")
        params['ответственный'] = filters['ответственный']

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
    SELECT
        c.id,
        c.external_code,
        c.contract_number,
        c.counterparty,
        c.amount,
        c.start_date,
        c.end_date,
        c.status,
        c.ответственный,
        c.цфо,
        c.условия_пролонгации,
        COALESCE(SUM(a.сумма_заявки) FILTER (
            WHERE a.статус_согласования IS NOT NULL
              AND a.статус_согласования != ''
              AND (a.состояние_заявки IS NULL
                   OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        ), 0) as spent
    FROM contracts c
    LEFT JOIN application_contracts ac ON ac.contract_id = c.id
    LEFT JOIN applications a ON a.номер_заявки = ac.application_number AND a.дата = ac.application_date
    {where_sql}
    GROUP BY c.id
    ORDER BY c.counterparty, c.contract_number;
    """
    df = read_sql(query, engine, params=params)

    today = date.today()

    try:
        forecast_map = {f['contract_id']: f for f in get_limits_forecast(days_horizon=60)}
    except Exception:
        forecast_map = {}

    rows = []
    for _, r in df.iterrows():
        has_end_date = pd.notna(r['end_date'])
        days_to_end = (r['end_date'] - today).days if has_end_date else None

        prolongation_raw = str(r['условия_пролонгации'] or '').strip().lower().rstrip('.')
        has_prolongation = prolongation_raw in PROLONGATION_VALUES

        expiring = (not has_prolongation) and has_end_date and 0 <= days_to_end <= 30
        overdue = (not has_prolongation) and has_end_date and days_to_end < 0
        limit_exceeded = (r['amount'] and float(r['amount']) > 0
                          and float(r['spent']) >= 0.9 * float(r['amount']))
        no_end_date = not has_end_date

        fc = forecast_map.get(int(r['id']))
        forecast_days = fc['days_to_exhaust'] if fc else None
        forecast_date = fc['exhaust_date'] if fc else None
        forecast_critical = fc['is_critical'] if fc else False

        flags = filters.get('flags') or []
        if flags:
            if 'expiring' in flags and not (expiring or overdue):
                continue
            if 'limit' in flags and not limit_exceeded:
                continue
            if 'no_end_date' in flags and not no_end_date:
                continue
            if 'forecast_critical' in flags and not forecast_critical:
                continue

        remainder = (float(r['amount']) - float(r['spent'])) if r['amount'] else 0.0

        rows.append({
            'id': int(r['id']),
            'external_code': r['external_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '',
            'amount': float(r['amount']) if r['amount'] else 0.0,
            'spent': float(r['spent']) if r['spent'] else 0.0,
            'remainder': remainder,
            'start_date': r['start_date'],
            'end_date': r['end_date'],
            'status': r['status'] or '',
            'ответственный': r['ответственный'] or '',
            'цфо': r['цфо'] or '',
            'условия_пролонгации': r['условия_пролонгации'] or '',
            'has_prolongation': has_prolongation,
            'expiring': expiring,
            'overdue': overdue,
            'limit_exceeded': limit_exceeded,
            'no_end_date': no_end_date,
            'forecast_days': forecast_days,
            'forecast_date': forecast_date,
            'forecast_critical': forecast_critical,
        })

    return {'contracts': rows}


def get_limits_forecast(days_horizon=60):
    """
    Прогноз исчерпания лимитов по активным договорам (с фильтром по ЦФО).
    """
    today = date.today()
    cfo = current_cfo()
    cfo_and = "AND c.цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    query = f"""
    WITH spends AS (
        SELECT 
            ac.contract_id,
            a.дата,
            a.сумма_заявки
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
    )
    SELECT 
        c.id,
        c.external_code,
        c.contract_number,
        c.counterparty,
        c.amount AS limit_amount,
        c.ответственный,
        c.цфо,
        c.end_date,
        COALESCE(SUM(s.сумма_заявки), 0) AS total_spent,
        MIN(s.дата) AS first_spend
    FROM contracts c
    LEFT JOIN spends s ON s.contract_id = c.id
    WHERE c.amount IS NOT NULL AND c.amount > 0
      {cfo_and}
    GROUP BY c.id;
    """
    df = read_sql(query, engine, params=params)

    rows = []
    for _, r in df.iterrows():
        limit_amount = float(r['limit_amount'])
        total_spent = float(r['total_spent'])
        remainder = limit_amount - total_spent

        if total_spent <= 0 or remainder <= 0 or pd.isna(r['first_spend']):
            continue

        first_spend = r['first_spend']
        if isinstance(first_spend, str):
            first_spend = pd.to_datetime(first_spend).date()

        days_elapsed = (today - first_spend).days
        if days_elapsed < 30:
            days_elapsed = 30
        if days_elapsed > 1095:
            days_elapsed = 1095

        daily_rate = total_spent / days_elapsed
        if daily_rate <= 0:
            continue

        days_to_exhaust = int(remainder / daily_rate)

        MAX_HORIZON_DAYS = 365 * 50
        if days_to_exhaust > MAX_HORIZON_DAYS:
            continue

        exhaust_date = today + timedelta(days=days_to_exhaust)
        is_critical = days_to_exhaust <= days_horizon

        rows.append({
            'contract_id': int(r['id']),
            'external_code': r['external_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '',
            'ответственный': r['ответственный'] or '',
            'цфо': r['цфо'] or '',
            'limit_amount': limit_amount,
            'total_spent': total_spent,
            'remainder': remainder,
            'daily_rate': round(daily_rate, 2),
            'days_to_exhaust': days_to_exhaust,
            'exhaust_date': exhaust_date,
            'is_critical': is_critical,
            'end_date': r['end_date'],
        })

    rows.sort(key=lambda x: (not x['is_critical'], x['days_to_exhaust']))
    return rows


# ==================== ДАШБОРД ЗАДОЛЖЕННОСТИ (KPI) ====================
def get_debts_summary():
    """Общие суммы КЗ, ДЗ и неоплаченных заявок + дата актуальности (с фильтром ЦФО)."""
    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    kz_total = read_sql(f"""
        SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
        WHERE вид_задолженности = 'Кредиторская' {cfo_and}
    """, engine, params=params).iloc[0, 0]

    dz_total = read_sql(f"""
        SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
        WHERE вид_задолженности = 'Дебиторская' {cfo_and}
    """, engine, params=params).iloc[0, 0]

    unpaid_apps = read_sql(f"""
        SELECT COALESCE(SUM(сумма_заявки),0)
        FROM applications
        WHERE оплачена = 'Нет'
          AND статус_согласования IS NOT NULL
          AND статус_согласования != ''
          AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')
          {cfo_and}
    """, engine, params=params).iloc[0, 0]

    imported_at = read_sql("SELECT MAX(imported_at) FROM debts", engine).iloc[0, 0]
    if pd.isna(imported_at):
        imported_at = None
    return {
        'kz_total': float(kz_total),
        'dz_total': float(dz_total),
        'unpaid_applications_total': float(unpaid_apps),
        'imported_at': imported_at,
    }


def get_cash_flow_forecast(horizon_days=90):
    """Прогноз денежного потока на N дней вперёд (с фильтром по ЦФО)."""
    today = date.today()
    horizon_date = today + timedelta(days=horizon_days)
    cfo = current_cfo()
    cfo_and = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    query = f"""
    SELECT 
        a.номер_заявки,
        a.дата,
        a.период_услуги,
        a.сумма_заявки,
        a.контрагент,
        a.ответственный,
        a.проект,
        COALESCE(a.период_услуги, a.дата + INTERVAL '21 days')::date AS expected_pay_date
    FROM applications a
    WHERE a.оплачена = 'Нет'
      AND a.статус_согласования IS NOT NULL
      AND a.статус_согласования != ''
      AND (a.состояние_заявки IS NULL 
           OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
      {cfo_and}
    """
    df = read_sql(query, engine, params=params)

    if df.empty:
        return {
            'weekly': [], 'monthly': [],
            'totals': {'30': 0, '60': 0, '90': 0, 'overdue': 0},
        }

    df['expected_pay_date'] = pd.to_datetime(df['expected_pay_date']).dt.date

    overdue_df = df[df['expected_pay_date'] < today]
    overdue_sum = float(overdue_df['сумма_заявки'].sum())

    horizon_df = df[(df['expected_pay_date'] >= today) & (df['expected_pay_date'] <= horizon_date)].copy()

    totals = {'overdue': overdue_sum, '30': 0.0, '60': 0.0, '90': 0.0}
    for days in (30, 60, 90):
        cutoff = today + timedelta(days=days)
        totals[str(days)] = float(
            df[(df['expected_pay_date'] >= today) & (df['expected_pay_date'] <= cutoff)]['сумма_заявки'].sum()
        )

    def week_label(d):
        return d - timedelta(days=d.weekday())

    horizon_df['week_start'] = horizon_df['expected_pay_date'].apply(week_label)
    weekly = (horizon_df
              .groupby('week_start', as_index=False)
              .agg(cnt=('номер_заявки', 'count'), total=('сумма_заявки', 'sum'))
              .sort_values('week_start'))
    weekly_records = [{
        'week_start': r['week_start'].strftime('%d.%m.%Y'),
        'week_end': (r['week_start'] + timedelta(days=6)).strftime('%d.%m.%Y'),
        'cnt': int(r['cnt']),
        'total': float(r['total']),
    } for _, r in weekly.iterrows()]

    horizon_df['month'] = horizon_df['expected_pay_date'].apply(lambda d: d.strftime('%Y-%m'))
    monthly = (horizon_df
               .groupby('month', as_index=False)
               .agg(cnt=('номер_заявки', 'count'), total=('сумма_заявки', 'sum'))
               .sort_values('month'))
    monthly_records = [{
        'month': r['month'],
        'cnt': int(r['cnt']),
        'total': float(r['total']),
    } for _, r in monthly.iterrows()]

    return {
        'weekly': weekly_records,
        'monthly': monthly_records,
        'totals': totals,
        'horizon_days': horizon_days,
    }


# ==================== СРЕДНИЕ РАСХОДЫ ====================
def _spending_period_range(period):
    """Возвращает start_date для периода. period: '6m' | '12m' | '24m' | 'all'."""
    today = date.today()
    if period == '6m':
        return today - timedelta(days=183)
    if period == '12m':
        return today - timedelta(days=365)
    if period == '24m':
        return today - timedelta(days=730)
    return None


def get_spending_analytics(period='12m'):
    """
    Средние расходы по проектам, контрагентам и договорам.
    Считаем все заявки (факт затрат), группируем по периоду_услуги.
    Исключаем аннулированные и подготовленные, фильтруем по ЦФО.
    """
    start_date = _spending_period_range(period)
    cfo = current_cfo()

    where = [
        "период_услуги IS NOT NULL",
        "(состояние_заявки IS NULL OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))",
    ]
    params = {}
    if cfo:
        where.append("цфо = %(user_cfo)s")
        params['user_cfo'] = cfo
    if start_date:
        where.append("период_услуги >= %(start)s")
        params['start'] = start_date

    where_sql = "WHERE " + " AND ".join(where)

    kpi_row = read_sql(f"""
        SELECT
            COUNT(*) AS cnt,
            COALESCE(SUM(сумма_заявки), 0) AS total,
            COUNT(DISTINCT контрагент) AS contractors,
            COUNT(DISTINCT проект) AS projects
        FROM applications
        {where_sql}
    """, engine, params=params).iloc[0]

    total = float(kpi_row['total'])
    cnt = int(kpi_row['cnt'])
    kpi = {
        'total': total,
        'count': cnt,
        'avg': total / cnt if cnt > 0 else 0.0,
        'contractors': int(kpi_row['contractors']),
        'projects': int(kpi_row['projects']),
    }

    monthly = read_sql(f"""
        SELECT 
            to_char(период_услуги, 'YYYY-MM') AS month,
            COUNT(*) AS cnt,
            COALESCE(SUM(сумма_заявки), 0) AS total
        FROM applications
        {where_sql}
        GROUP BY month
        ORDER BY month
    """, engine, params=params).to_dict('records')

    by_project = read_sql(f"""
        WITH agg AS (
            SELECT 
                COALESCE(NULLIF(проект, ''), 'Внутренние нужды (расходы головного и сервисных офисов)') AS project,
                COUNT(*) AS cnt,
                COALESCE(SUM(сумма_заявки), 0) AS total
            FROM applications
            {where_sql}
            GROUP BY project
        ),
        top_contractor AS (
            SELECT DISTINCT ON (project) project, контрагент
            FROM (
                SELECT 
                    COALESCE(NULLIF(проект, ''), 'Внутренние нужды (расходы головного и сервисных офисов)') AS project,
                    контрагент,
                    SUM(сумма_заявки) AS s
                FROM applications
                {where_sql}
                GROUP BY project, контрагент
            ) t
            ORDER BY project, s DESC
        )
        SELECT 
            a.project, a.cnt, a.total,
            a.total / a.cnt AS avg_check,
            tc.контрагент AS top_contractor
        FROM agg a
        LEFT JOIN top_contractor tc ON tc.project = a.project
        ORDER BY a.total DESC
    """, engine, params=params).to_dict('records')

    by_contractor = read_sql(f"""
        WITH agg AS (
            SELECT 
                контрагент,
                COUNT(*) AS cnt,
                COALESCE(SUM(сумма_заявки), 0) AS total
            FROM applications
            {where_sql}
            GROUP BY контрагент
        ),
        top_project AS (
            SELECT DISTINCT ON (контрагент) контрагент, project
            FROM (
                SELECT 
                    контрагент,
                    COALESCE(NULLIF(проект, ''), 'Внутренние нужды (расходы головного и сервисных офисов)') AS project,
                    SUM(сумма_заявки) AS s
                FROM applications
                {where_sql}
                GROUP BY контрагент, project
            ) t
            ORDER BY контрагент, s DESC
        )
        SELECT 
            a.контрагент, a.cnt, a.total,
            a.total / a.cnt AS avg_check,
            tp.project AS top_project
        FROM agg a
        LEFT JOIN top_project tp ON tp.контрагент = a.контрагент
        ORDER BY a.total DESC
        LIMIT 100
    """, engine, params=params).to_dict('records')

    # В части договоров фильтр по ЦФО применяется и к contracts
    cfo_contract = "AND c.цфо = %(user_cfo)s" if cfo else ""
    by_contract = read_sql(f"""
        SELECT 
            c.external_code,
            c.contract_number,
            c.counterparty,
            c.amount AS limit_amount,
            COUNT(a.номер_заявки) AS cnt,
            COALESCE(SUM(a.сумма_заявки), 0) AS total,
            COALESCE(SUM(a.сумма_заявки), 0) / NULLIF(COUNT(a.номер_заявки), 0) AS avg_check,
            CASE 
                WHEN c.amount > 0 THEN
                    COALESCE(SUM(a.сумма_заявки), 0) * 100.0 / c.amount
                ELSE NULL
            END AS usage_pct
        FROM contracts c
        JOIN application_contracts ac ON ac.contract_id = c.id
        JOIN applications a 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.период_услуги IS NOT NULL
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
          {"AND a.период_услуги >= %(start)s" if start_date else ""}
          {cfo_contract}
        GROUP BY c.id
        HAVING COUNT(a.номер_заявки) > 0
        ORDER BY total DESC
        LIMIT 100
    """, engine, params=params).to_dict('records')

    return {
        'kpi': kpi,
        'monthly': monthly,
        'by_project': by_project,
        'by_contractor': by_contractor,
        'by_contract': by_contract,
        'period': period,
    }


# ==================== ПОРТФЕЛЬ ДОГОВОРОВ ====================
def get_contracts_portfolio():
    """
    Портфель договоров «требует внимания».
    4 категории: dead, growing, expiring, mismatched.
    С фильтром по ЦФО пользователя.
    """
    today = date.today()
    cfo = current_cfo()
    cfo_and_c = "AND c.цфо = %(user_cfo)s" if cfo else ""
    cfo_and_d = "AND d.цфо = %(user_cfo)s" if cfo else ""
    cfo_and_a = "AND a.цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    # ---------- Базовый список активных договоров ----------
    base_query = f"""
    SELECT 
        c.id,
        c.external_code,
        c.contract_number,
        c.counterparty,
        c.amount,
        c.start_date,
        c.end_date,
        c.ответственный,
        c.цфо,
        c.условия_пролонгации,
        COALESCE(SUM(a.сумма_заявки) FILTER (
            WHERE a.статус_согласования IS NOT NULL
              AND a.статус_согласования != ''
              AND (a.состояние_заявки IS NULL 
                   OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        ), 0) AS total_spent,
        MAX(a.дата) AS last_application_date
    FROM contracts c
    LEFT JOIN application_contracts ac ON ac.contract_id = c.id
    LEFT JOIN applications a 
        ON a.номер_заявки = ac.application_number 
       AND a.дата = ac.application_date
    WHERE 1=1 {cfo_and_c}
    GROUP BY c.id;
    """
    df = read_sql(base_query, engine, params=params)

    dead = []
    growing = []
    expiring = []

    for _, r in df.iterrows():
        has_end_date = pd.notna(r['end_date'])
        end_date = r['end_date'] if has_end_date else None
        last_app = r['last_application_date']
        if isinstance(last_app, str):
            last_app = pd.to_datetime(last_app).date()

        prolongation_raw = str(r['условия_пролонгации'] or '').strip().lower().rstrip('.')
        has_prolongation = prolongation_raw in PROLONGATION_VALUES

        info = {
            'external_code': r['external_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '',
            'amount': float(r['amount']) if r['amount'] else 0.0,
            'total_spent': float(r['total_spent']) if r['total_spent'] else 0.0,
            'end_date': end_date,
            'ответственный': r['ответственный'] or '',
            'цфо': r['цфо'] or '',
        }

        is_active = (end_date is None) or (end_date >= today)
        if is_active and last_app:
            days_since_last = (today - last_app).days
            if days_since_last > 180:
                info['last_application_date'] = last_app
                info['days_since_last'] = days_since_last
                dead.append(info)
        elif is_active and not last_app and r['start_date'] and pd.notna(r['start_date']):
            start = r['start_date']
            if isinstance(start, str):
                start = pd.to_datetime(start).date()
            days_since_start = (today - start).days
            if days_since_start > 180:
                info['last_application_date'] = None
                info['days_since_last'] = days_since_start
                dead.append(info)

        if has_end_date and not has_prolongation:
            days_to_end = (end_date - today).days
            if 0 <= days_to_end <= 60:
                info['days_to_end'] = days_to_end
                expiring.append(info)

    # --- Растущие ---
    growing_query = f"""
    WITH recent AS (
        SELECT 
            ac.contract_id,
            SUM(a.сумма_заявки) AS total_3m
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.дата >= NOW() - INTERVAL '3 months'
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        GROUP BY ac.contract_id
    ),
    previous AS (
        SELECT 
            ac.contract_id,
            SUM(a.сумма_заявки) AS total_prev_3m
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        WHERE a.дата >= NOW() - INTERVAL '6 months'
          AND a.дата < NOW() - INTERVAL '3 months'
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        GROUP BY ac.contract_id
    )
    SELECT 
        c.id,
        c.external_code,
        c.contract_number,
        c.counterparty,
        c.amount,
        c.end_date,
        c.ответственный,
        c.цфо,
        COALESCE(r.total_3m, 0) AS total_3m,
        COALESCE(p.total_prev_3m, 0) AS total_prev_3m
    FROM contracts c
    JOIN recent r ON r.contract_id = c.id
    LEFT JOIN previous p ON p.contract_id = c.id
    WHERE COALESCE(r.total_3m, 0) > 0
      AND COALESCE(p.total_prev_3m, 0) > 0
      AND r.total_3m >= p.total_prev_3m * 1.5
      AND r.total_3m >= 100000
      {cfo_and_c}
    ORDER BY (r.total_3m - COALESCE(p.total_prev_3m, 0)) DESC
    LIMIT 50;
    """
    growing_df = read_sql(growing_query, engine, params=params)
    for _, r in growing_df.iterrows():
        growing.append({
            'external_code': r['external_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '',
            'amount': float(r['amount']) if r['amount'] else 0.0,
            'total_3m': float(r['total_3m']),
            'total_prev_3m': float(r['total_prev_3m']),
            'growth_pct': (float(r['total_3m']) / float(r['total_prev_3m']) - 1) * 100,
            'end_date': r['end_date'],
            'ответственный': r['ответственный'] or '',
        })

    # --- С расхождениями ---
    mismatched_query = f"""
    WITH kz AS (
        SELECT d.договор_код, SUM(d.сумма_остаток) AS kz_sum
        FROM debts d
        WHERE d.вид_задолженности = 'Кредиторская'
          {cfo_and_d}
        GROUP BY d.договор_код
    ),
    apps AS (
        SELECT 
            c.external_code AS code, 
            SUM(a.сумма_заявки) AS apps_sum
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        JOIN contracts c ON c.id = ac.contract_id
        WHERE a.оплачена = 'Нет'
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
          {cfo_and_c}
        GROUP BY c.external_code
    )
    SELECT 
        COALESCE(k.договор_код, a.code) AS contract_code,
        c.contract_number,
        COALESCE(
            NULLIF(c.counterparty, ''),
            NULLIF(c.counterparty, 'nan'),
            NULLIF(d.контрагент, ''),
            NULLIF(d.контрагент, 'nan'),
            '—'
        ) AS counterparty,
        COALESCE(k.kz_sum, 0) AS kz_sum,
        COALESCE(a.apps_sum, 0) AS apps_sum,
        COALESCE(k.kz_sum, 0) - COALESCE(a.apps_sum, 0) AS diff
    FROM kz k
    FULL OUTER JOIN apps a ON k.договор_код = a.code
    LEFT JOIN contracts c ON c.external_code = COALESCE(k.договор_код, a.code)
    LEFT JOIN LATERAL (
        SELECT контрагент 
        FROM debts 
        WHERE договор_код = COALESCE(k.договор_код, a.code)
          AND контрагент IS NOT NULL 
          AND контрагент != '' 
          AND контрагент != 'nan'
        LIMIT 1
    ) d ON TRUE
    WHERE ABS(COALESCE(k.kz_sum, 0) - COALESCE(a.apps_sum, 0)) > 10000
    ORDER BY ABS(COALESCE(k.kz_sum, 0) - COALESCE(a.apps_sum, 0)) DESC
    LIMIT 50;
    """
    mismatched_df = read_sql(mismatched_query, engine, params=params)
    mismatched = []
    for _, r in mismatched_df.iterrows():
        mismatched.append({
            'contract_code': r['contract_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '—',
            'kz_sum': float(r['kz_sum']),
            'apps_sum': float(r['apps_sum']),
            'diff': float(r['diff']),
        })

    dead.sort(key=lambda x: -x['days_since_last'])
    expiring.sort(key=lambda x: x['days_to_end'])

    kpi = {
        'dead_count': len(dead),
        'growing_count': len(growing),
        'expiring_count': len(expiring),
        'mismatched_count': len(mismatched),
    }

    return {
        'dead': dead[:30],
        'growing': growing,
        'expiring': expiring[:50],
        'mismatched': mismatched,
        'kpi': kpi,
    }