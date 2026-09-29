import logging
import json
from datetime import date, timedelta
from sqlalchemy import text
import pandas as pd
from modules.core.utils import engine, current_cfo, normalize_doc_ref, split_doc_refs, read_sql

logger = logging.getLogger(__name__)


def link_all_applications():
    """
    Пересобирает application_contracts по совпадению:
        applications.договор_код = contracts.external_code.
    Затем для каждого договора проставляет ответственного — самого
    частого среди связанных заявок.
    """
    logger.info("Link: старт пересборки связей...")

    with engine.connect() as conn:
        # 1. Пересобираем связи
        conn.execute(text("DELETE FROM application_contracts;"))
        conn.execute(text("""
            INSERT INTO application_contracts 
                (application_number, application_date, contract_id)
            SELECT a.номер_заявки, a.дата, c.id
            FROM applications a
            JOIN contracts c ON c.external_code = a.договор_код
            WHERE a.договор_код IS NOT NULL AND a.договор_код != ''
            ON CONFLICT DO NOTHING;
        """))
        conn.commit()

        # 2. Считаем количество связей
        count = conn.execute(text("SELECT count(*) FROM application_contracts")).scalar()
        logger.info(f"Link: связей создано {count}")

        # 3. Обновляем ответственного по договорам:
        #    берём самого частого ответственного среди заявок этого договора
        conn.execute(text("""
            UPDATE contracts c
            SET ответственный = sub.resp
            FROM (
                SELECT ac.contract_id, a.ответственный AS resp,
                       ROW_NUMBER() OVER (
                           PARTITION BY ac.contract_id
                           ORDER BY COUNT(*) DESC, MAX(a.дата) DESC
                       ) AS rn
                FROM applications a
                JOIN application_contracts ac
                    ON a.номер_заявки = ac.application_number
                   AND a.дата = ac.application_date
                WHERE a.ответственный IS NOT NULL
                  AND a.ответственный != ''
                GROUP BY ac.contract_id, a.ответственный
            ) sub
            WHERE c.id = sub.contract_id AND sub.rn = 1;
        """))
        # 4. Обновляем ЦФО по договорам из связанных заявок
        conn.execute(text("""
            UPDATE contracts c
            SET цфо = sub.cfo
            FROM (
                SELECT ac.contract_id, a.цфо AS cfo,
                       ROW_NUMBER() OVER (
                           PARTITION BY ac.contract_id
                           ORDER BY COUNT(*) DESC, MAX(a.дата) DESC
                       ) AS rn
                FROM applications a
                JOIN application_contracts ac
                    ON a.номер_заявки = ac.application_number
                   AND a.дата = ac.application_date
                WHERE a.цфо IS NOT NULL AND a.цфо != ''
                GROUP BY ac.contract_id, a.цфо
            ) sub
            WHERE c.id = sub.contract_id AND sub.rn = 1;
        """))
        conn.commit()

    logger.info("Link: ответственные по договорам обновлены")


def _extract_link_tokens(text):
    """
    Извлекает значимые токены для сопоставления заявок с договорами:
      - STG-номера:        stg000624
      - Номера договоров:  159991/nic-d, стнг-усл-14427, 13842/t
      - Длинные числа:     03020429, 0302042
    Исключаем слова, предлоги, короткие числа.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return set()
    s = str(text).lower()
    s = s.replace('\xa0', ' ').replace('\u202f', ' ').replace('\u2009', ' ')

    tokens = set()

    # STG-номера
    for m in re.finditer(r'(stg\d{5,})', s):
        tokens.add(m.group(1))

    # Буквенно-цифровые коды: содержат и буквы, и цифры, длина ≥ 6
    # Примеры: "стнг-усл-14427", "159991/nic-d", "13842/t", "апс-усл-01032"
    for m in re.finditer(
        r'([a-zа-я]{2,}[a-zа-я0-9]*[-\s/.]*[a-zа-я0-9]*\d{3,}[a-zа-я0-9/.-]*)',
        s
    ):
        tok = re.sub(r'[\s.]+', '', m.group(1))
        if len(tok) >= 6:
            tokens.add(tok)

    # Также любые "сложные" коды типа 159991/NIC-D (буквы+цифры+слеш)
    for m in re.finditer(r'(\d{4,}[a-zа-я/.-]+[a-zа-я0-9]+)', s):
        tok = m.group(1)
        if len(tok) >= 6:
            tokens.add(tok)

    # Длинные числа (от 7 цифр) — специфичны, обычно уникальны
    for m in re.finditer(r'\b(\d{7,})\b', s):
        tokens.add(m.group(1))

    return tokens

# ==================== ДОГОВОРЫ + РАСЧЁТЫ ====================

PROLONGATION_VALUES = {
    'автоматически на год',
    'автоматически на неопределенный срок',
    'автоматически на неопределённый срок',
    'допускает продление',
}


def _cfo_where(alias='c'):
    """Возвращает (sql_and, params) для фильтра по ЦФО."""
    cfo = current_cfo()
    if not cfo:
        return '', {}
    return f"AND {alias}.цфо = %(user_cfo)s", {'user_cfo': cfo}


def get_contracts_list(filters=None):
    """
    Основная таблица: договоры + лимит + КЗ + ДЗ + расхождения.
    """
    filters = filters or {}
    cfo_and, params = _cfo_where('c')

    where = ["1=1"]
    if filters.get('ответственный'):
        where.append("c.ответственный = %(ответственный)s")
        params['ответственный'] = filters['ответственный']
    where_sql = "WHERE " + " AND ".join(where)

    query = f"""
    WITH spent AS (
        SELECT 
            ac.contract_id,
            SUM(a.сумма_заявки) FILTER (
                WHERE a.статус_согласования IS NOT NULL
                  AND a.статус_согласования != ''
                  AND (a.состояние_заявки IS NULL 
                       OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
            ) AS spent_amount,
            MAX(a.дата) AS last_app_date
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        GROUP BY ac.contract_id
    ),
    kz_dz AS (
        SELECT 
            договор_код,
            SUM(сумма_остаток) FILTER (WHERE вид_задолженности = 'Кредиторская') AS kz,
            SUM(сумма_остаток) FILTER (WHERE вид_задолженности = 'Дебиторская') AS dz
        FROM debts
        GROUP BY договор_код
    ),
    unpaid AS (
        SELECT 
            c2.external_code AS code,
            SUM(a.сумма_заявки) AS unpaid_sum,
            bool_or(a.признак_оплаты ILIKE 'Аванс%%') AS has_advance,
            bool_or(a.признак_оплаты IS NOT NULL 
                    AND a.признак_оплаты != '' 
                    AND a.признак_оплаты NOT ILIKE 'Аванс%%') AS has_repayment
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        JOIN contracts c2 ON c2.id = ac.contract_id
        WHERE a.оплачена = 'Нет'
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        GROUP BY c2.external_code
    )
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
        COALESCE(s.spent_amount, 0) AS spent,
        s.last_app_date,
        COALESCE(k.kz, 0) AS kz,
        COALESCE(k.dz, 0) AS dz,
        COALESCE(u.unpaid_sum, 0) AS unpaid_sum,
        COALESCE(u.has_advance, FALSE) AS has_advance,
        COALESCE(u.has_repayment, FALSE) AS has_repayment
    FROM contracts c
    LEFT JOIN spent s ON s.contract_id = c.id
    LEFT JOIN kz_dz k ON k.договор_код = c.external_code
    LEFT JOIN unpaid u ON u.code = c.external_code
    {where_sql}
      {cfo_and}
    ORDER BY c.counterparty NULLS LAST, c.contract_number NULLS LAST
    """
    df = read_sql(query, engine, params=params)

    today = date.today()

    # Прогноз исчерпания (один раз)
    try:
        from modules.dashboard.services import get_limits_forecast
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
        diff = float(r['kz']) - float(r['unpaid_sum'])
        has_mismatch = abs(diff) > 1

        fc = forecast_map.get(int(r['id']))
        forecast_date = fc['exhaust_date'] if fc else None
        forecast_critical = fc['is_critical'] if fc else False

        # Фильтр по галочкам
        flags = filters.get('flags') or []
        if flags:
            if 'expiring' in flags and not (expiring or overdue):
                continue
            if 'limit' in flags and not limit_exceeded:
                continue
            if 'mismatch' in flags and not has_mismatch:
                continue
            if 'forecast_critical' in flags and not forecast_critical:
                continue

        # Фильтр по признаку оплаты
        payment_mode = filters.get('payment_mode')
        if payment_mode == 'advance' and not r['has_advance']:
            continue
        if payment_mode == 'repayment' and not r['has_repayment']:
            continue

        rows.append({
            'id': int(r['id']),
            'external_code': r['external_code'] or '',
            'contract_number': r['contract_number'] or '',
            'counterparty': r['counterparty'] or '',
            'amount': float(r['amount']) if r['amount'] else 0.0,
            'spent': float(r['spent']) if r['spent'] else 0.0,
            'remainder': (float(r['amount']) - float(r['spent'])) if r['amount'] else 0.0,
            'kz': float(r['kz']),
            'dz': float(r['dz']),
            'unpaid_sum': float(r['unpaid_sum']),
            'diff': diff,
            'has_advance': bool(r['has_advance']),
            'has_repayment': bool(r['has_repayment']),
            'end_date': r['end_date'],
            'start_date': r['start_date'],
            'ответственный': r['ответственный'] or '',
            'цфо': r['цфо'] or '',
            'условия_пролонгации': r['условия_пролонгации'] or '',
            'has_prolongation': has_prolongation,
            'expiring': expiring,
            'overdue': overdue,
            'limit_exceeded': limit_exceeded,
            'no_end_date': no_end_date,
            'has_mismatch': has_mismatch,
            'forecast_date': forecast_date,
            'forecast_critical': forecast_critical,
        })

    return rows


def get_contracts_filter_options():
    """Список ответственных для фильтра."""
    cfo_and, params = _cfo_where('c')
    df = read_sql(f"""
        SELECT DISTINCT ответственный FROM contracts c
        WHERE ответственный IS NOT NULL AND ответственный != ''
          {cfo_and}
        ORDER BY ответственный
    """, engine, params=params)
    return {'responsibles': df['ответственный'].tolist()}


def get_contract_details(contract_code):
    """
    Данные по договору: информация, KPI, сверка по документам расчётов.
    """
    cfo = current_cfo()

    contract = read_sql("""
        SELECT * FROM contracts WHERE external_code = %(code)s LIMIT 1
    """, engine, params={'code': contract_code})

    if cfo and not contract.empty:
        if (contract.iloc[0]['цфо'] or '') != cfo:
            return {
                'contract_code': contract_code,
                'contract_info': None,
                'kz_total': 0.0, 'dz_total': 0.0,
                'unpaid_sum': 0.0, 'diff': 0.0,
                'reconciliation': [],
            }

    kz_total = 0.0
    dz_total = 0.0
    unpaid_sum = 0.0

    if not contract.empty:
        cid = int(contract.iloc[0]['id'])

        kz_row = read_sql("""
            SELECT COALESCE(SUM(сумма_остаток),0) AS s
            FROM debts
            WHERE договор_код = %(code)s AND вид_задолженности = 'Кредиторская'
        """, engine, params={'code': contract_code}).iloc[0]
        kz_total = float(kz_row['s'])

        dz_row = read_sql("""
            SELECT COALESCE(SUM(сумма_остаток),0) AS s
            FROM debts
            WHERE договор_код = %(code)s AND вид_задолженности = 'Дебиторская'
        """, engine, params={'code': contract_code}).iloc[0]
        dz_total = float(dz_row['s'])

        apps_sum = read_sql("""
            SELECT COALESCE(SUM(a.сумма_заявки),0) AS s
            FROM applications a
            JOIN application_contracts ac 
                ON a.номер_заявки = ac.application_number 
               AND a.дата = ac.application_date
            WHERE ac.contract_id = %(cid)s
              AND a.оплачена = 'Нет'
              AND a.статус_согласования IS NOT NULL
              AND a.статус_согласования != ''
              AND (a.состояние_заявки IS NULL 
                   OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
        """, engine, params={'cid': cid}).iloc[0]
        unpaid_sum = float(apps_sum['s'])

    debts = read_sql("""
        SELECT id, вид_задолженности, документ_расчетов,
               номер_документа, дата_документа, сумма_остаток
        FROM debts WHERE договор_код = %(code)s
    """, engine, params={'code': contract_code})

    apps = read_sql("""
        SELECT a.номер_заявки, a.дата, a.сумма_заявки,
               a.документ_расчетов_с_контрагентом
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        JOIN contracts c ON c.id = ac.contract_id
        WHERE c.external_code = %(code)s
          AND a.оплачена = 'Нет'
          AND a.статус_согласования IS NOT NULL
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL 
               OR a.состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
    """, engine, params={'code': contract_code})

    if not debts.empty:
        debts['doc_key'] = debts['документ_расчетов'].apply(normalize_doc_ref)
    else:
        debts['doc_key'] = []

    if not apps.empty:
        apps['doc_keys'] = apps['документ_расчетов_с_контрагентом'].apply(split_doc_refs)
    else:
        apps['doc_keys'] = []

    apps_exp = apps.explode('doc_keys') if not apps.empty else apps

    rows = []
    app_pairs_used = set()

    for _, d in debts.iterrows():
        key = d['doc_key']
        matched = pd.DataFrame()
        if key and not apps_exp.empty:
            matched = apps_exp[apps_exp['doc_keys'] == key]

        if not matched.empty:
            for _, a in matched.iterrows():
                app_pairs_used.add((a['номер_заявки'], a['дата'], a['doc_keys']))
                rows.append({
                    'doc_number': d['номер_документа'] or '',
                    'doc_ref': d['документ_расчетов'] or '',
                    'doc_date': d['дата_документа'],
                    'app_number': a['номер_заявки'],
                    'app_date': a['дата'],
                    'debt_amount': float(d['сумма_остаток']),
                    'app_amount': float(a['сумма_заявки']),
                    'view_type': d['вид_задолженности'] or '',
                    'matched': True,
                })
        else:
            rows.append({
                'doc_number': d['номер_документа'] or '',
                'doc_ref': d['документ_расчетов'] or '',
                'doc_date': d['дата_документа'],
                'app_number': '',
                'app_date': None,
                'debt_amount': float(d['сумма_остаток']),
                'app_amount': 0.0,
                'view_type': d['вид_задолженности'] or '',
                'matched': False,
            })

    debt_keys = set(debts['doc_key'].dropna()) if not debts.empty else set()

    if not apps.empty:
        for _, a in apps.iterrows():
            keys = a['doc_keys']
            if not keys:
                continue
            already = any(
                (a['номер_заявки'], a['дата'], k) in app_pairs_used
                for k in keys
            )
            if already:
                continue
            if any(k in debt_keys for k in keys):
                continue
            rows.append({
                'doc_number': '',
                'doc_ref': a['документ_расчетов_с_контрагентом'] or '',
                'doc_date': None,
                'app_number': a['номер_заявки'],
                'app_date': a['дата'],
                'debt_amount': 0.0,
                'app_amount': float(a['сумма_заявки']),
                'view_type': '',
                'matched': False,
            })

    rows.sort(key=lambda x: (
        1 if x['matched'] else 0,
        x['doc_date'] or date(1900, 1, 1),
        x['app_date'] or date(1900, 1, 1),
    ), reverse=True)

    return {
        'contract_code': contract_code,
        'contract_info': contract.to_dict('records')[0] if not contract.empty else None,
        'kz_total': kz_total,
        'dz_total': dz_total,
        'unpaid_sum': unpaid_sum,
        'diff': kz_total - unpaid_sum,
        'reconciliation': rows,
    }