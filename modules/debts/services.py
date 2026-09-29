from datetime import date
import pandas as pd
from modules.core.utils import engine, normalize_doc_ref, split_doc_refs, current_cfo, read_sql

def get_debts_summary():
    from modules.core.utils import current_cfo
    cfo = current_cfo()
    cfo_and_debts = "AND цфо = %(user_cfo)s" if cfo else ""
    cfo_and_apps = "AND цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    kz_total = read_sql(f"""
        SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
        WHERE вид_задолженности = 'Кредиторская' {cfo_and_debts}
    """, engine, params=params).iloc[0, 0]

    dz_total = read_sql(f"""
        SELECT COALESCE(SUM(сумма_остаток),0) FROM debts
        WHERE вид_задолженности = 'Дебиторская' {cfo_and_debts}
    """, engine, params=params).iloc[0, 0]

    unpaid_apps = read_sql(f"""
        SELECT COALESCE(SUM(сумма_заявки),0)
        FROM applications
        WHERE оплачена = 'Нет'
          AND статус_согласования IS NOT NULL
          AND статус_согласования != ''
          AND (состояние_заявки IS NULL OR состояние_заявки != 'Аннулирован')
          {cfo_and_apps}
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

def get_reconciliation_table():
    """
    Сводная таблица по договорам: КЗ, ДЗ, неоплаченные заявки,
    признак оплаты (флаг аванс/погашение), расхождение.
    Фильтруется по ЦФО пользователя.
    """
    from modules.core.utils import current_cfo
    cfo = current_cfo()
    cfo_and_debts = "AND d.цфо = %(user_cfo)s" if cfo else ""
    cfo_and_apps = "AND a.цфо = %(user_cfo)s" if cfo else ""
    params = {'user_cfo': cfo} if cfo else {}

    query = f"""
    WITH debts_agg AS (
        SELECT 
            d.договор_код,
            d.договор_наименование,
            d.контрагент,
            SUM(CASE WHEN d.вид_задолженности = 'Кредиторская' THEN d.сумма_остаток ELSE 0 END) AS kz,
            SUM(CASE WHEN d.вид_задолженности = 'Дебиторская' THEN d.сумма_остаток ELSE 0 END) AS dz,
            COUNT(*) AS debts_count
        FROM debts d
        WHERE 1=1 {cfo_and_debts}
        GROUP BY d.договор_код, d.договор_наименование, d.контрагент
    ),
    apps_agg AS (
        SELECT 
            c.external_code AS contract_code,
            SUM(a.сумма_заявки) AS unpaid_sum,
            COUNT(*) AS apps_count,
            bool_or(a.признак_оплаты ILIKE 'Аванс%%') AS has_advance,
            bool_or(a.признак_оплаты IS NOT NULL 
                    AND a.признак_оплаты != '' 
                    AND a.признак_оплаты NOT ILIKE 'Аванс%%') AS has_repayment
        FROM applications a
        JOIN application_contracts ac 
            ON a.номер_заявки = ac.application_number 
           AND a.дата = ac.application_date
        JOIN contracts c ON c.id = ac.contract_id
        WHERE a.оплачена = 'Нет'
          AND a.статус_согласования IS NOT NULL 
          AND a.статус_согласования != ''
          AND (a.состояние_заявки IS NULL OR a.состояние_заявки != 'Аннулирован')
          {cfo_and_apps}
        GROUP BY c.external_code
    )
    SELECT 
        COALESCE(d.договор_код, a.contract_code) AS contract_code,
        d.договор_наименование,
        d.контрагент,
        COALESCE(d.kz, 0) AS kz,
        COALESCE(d.dz, 0) AS dz,
        COALESCE(a.unpaid_sum, 0) AS unpaid_sum,
        COALESCE(a.has_advance, FALSE) AS has_advance,
        COALESCE(a.has_repayment, FALSE) AS has_repayment,
        COALESCE(d.debts_count, 0) AS debts_count,
        COALESCE(a.apps_count, 0) AS apps_count,
        COALESCE(d.kz, 0) - COALESCE(a.unpaid_sum, 0) AS diff
    FROM debts_agg d
    FULL OUTER JOIN apps_agg a ON d.договор_код = a.contract_code
    ORDER BY ABS(COALESCE(d.kz, 0) - COALESCE(a.unpaid_sum, 0)) DESC;
    """
    return read_sql(query, engine, params=params)

def get_contract_details(contract_code):
    """
    Данные по договору:
      - информация о договоре
      - KPI (КЗ, ДЗ, неоплаченные заявки, расхождение)
      - сверка по документам расчётов (одна таблица)
    """
    from modules.core.utils import current_cfo
    cfo = current_cfo()

    contract = read_sql("""
        SELECT * FROM contracts WHERE external_code = %(code)s LIMIT 1
    """, engine, params={'code': contract_code})

    # Проверка ЦФО
    if cfo and not contract.empty:
        if (contract.iloc[0]['цфо'] or '') != cfo:
            return {
                'contract_code': contract_code,
                'contract_info': None,
                'kz_total': 0.0, 'dz_total': 0.0,
                'unpaid_sum': 0.0, 'diff': 0.0,
                'reconciliation': [],
            }

    # KPI
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

    # --- Строки задолженности ---
    debts = read_sql("""
        SELECT 
            id,
            вид_задолженности,
            документ_расчетов,
            номер_документа,
            дата_документа,
            сумма_остаток
        FROM debts
        WHERE договор_код = %(code)s
    """, engine, params={'code': contract_code})

    # --- Заявки (неоплаченные) ---
    apps = read_sql("""
        SELECT 
            a.номер_заявки,
            a.дата,
            a.сумма_заявки,
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

    # Нормализация
    if not debts.empty:
        debts['doc_key'] = debts['документ_расчетов'].apply(normalize_doc_ref)
    else:
        debts['doc_key'] = []

    if not apps.empty:
        apps['doc_keys'] = apps['документ_расчетов_с_контрагентом'].apply(split_doc_refs)
    else:
        apps['doc_keys'] = []

    # Разворачиваем заявки по ключам
    if not apps.empty:
        apps_exp = apps.explode('doc_keys')
    else:
        apps_exp = apps

    # Собираем сверку
    rows = []
    debt_ids_used = set()
    app_pairs_used = set()  # (номер, дата, ключ)

    # 1. По каждой строке задолженности ищем заявки с таким же ключом
    for _, d in debts.iterrows():
        key = d['doc_key']
        debt_ids_used.add(d['id'])

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
            # Строка только в задолженности
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

    # 2. Заявки, чьи документы не нашли совпадений в задолженности
    debt_keys = set(debts['doc_key'].dropna()) if not debts.empty else set()

    if not apps.empty:
        for _, a in apps.iterrows():
            keys = a['doc_keys']
            if not keys:
                continue
            # Если хотя бы один ключ уже сматчился через debts — эта заявка уже в rows
            already = any(
                (a['номер_заявки'], a['дата'], k) in app_pairs_used
                for k in keys
            )
            if already:
                continue

            # Проверяем, есть ли ключи в debt_keys
            if any(k in debt_keys for k in keys):
                continue

            # Заявка-сирота: показываем её строку
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

    # Сортировка: сначала unmatched, потом по дате документа
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

def get_debts_list(view_type=None, contract_code=None):
    from modules.core.utils import current_cfo
    cfo = current_cfo()
    where = []
    params = {'user_cfo': cfo} if cfo else {}
    if cfo:
        where.append("цфо = %(user_cfo)s")
    if view_type:
        where.append("вид_задолженности = %(вид)s")
        params['вид'] = view_type
    if contract_code:
        where.append("договор_код = %(код)s")
        params['код'] = contract_code
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    query = f"""
        SELECT вид_задолженности, контрагент, договор_код, договор_наименование,
               номер_документа, дата_документа, документ_расчетов,
               период_погашения, дней_просрочки, сумма_остаток, проект, цфо
        FROM debts
        {where_sql}
        ORDER BY вид_задолженности, контрагент, период_погашения
    """
    return read_sql(query, engine, params=params)