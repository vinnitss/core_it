"""
Генератор SQL для конструктора отчётов.
Поддерживает табличные и KPI-отчёты, фильтрацию по ЦФО, агрегации.
"""
from modules.report_builder.meta import DATA_SOURCES, OPERATORS


class ReportBuilderError(Exception):
    pass


def _validate_field(source_meta, field_name):
    if field_name not in {f['name'] for f in source_meta['fields']}:
        raise ReportBuilderError(f"Неизвестное поле: {field_name}")
    return next(f for f in source_meta['fields'] if f['name'] == field_name)


def _build_where(source_meta, filters, params, user_cfo, apply_cfo=True):
    """Строит WHERE-условие. Добавляет фильтр по ЦФО, если задан."""
    where_parts = []

    # Фильтр по ЦФО пользователя
    if apply_cfo and user_cfo and source_meta.get('cfo_field'):
        where_parts.append(f"{source_meta['cfo_field']} = %(user_cfo)s")
        params['user_cfo'] = user_cfo

    # Пользовательские фильтры
    for i, f in enumerate(filters or []):
        field_name = f.get('field')
        op = f.get('op')
        value = f.get('value')
        value2 = f.get('value2')

        fmeta = _validate_field(source_meta, field_name)
        allowed_ops = {o['value'] for o in OPERATORS.get(fmeta['type'], [])}
        if op not in allowed_ops:
            raise ReportBuilderError(f"Оператор '{op}' недопустим для поля '{field_name}'")

        p = f"f_{i}"
        if op == 'eq':
            where_parts.append(f"{field_name} = %({p})s")
            params[p] = value
        elif op == 'neq':
            where_parts.append(f"{field_name} != %({p})s")
            params[p] = value
        elif op == 'contains':
            where_parts.append(f"{field_name} ILIKE %({p})s")
            params[p] = f"%{value}%"
        elif op == 'not_contains':
            where_parts.append(f"{field_name} NOT ILIKE %({p})s")
            params[p] = f"%{value}%"
        elif op == 'gt':
            where_parts.append(f"{field_name} > %({p})s")
            params[p] = value
        elif op == 'gte':
            where_parts.append(f"{field_name} >= %({p})s")
            params[p] = value
        elif op == 'lt':
            where_parts.append(f"{field_name} < %({p})s")
            params[p] = value
        elif op == 'lte':
            where_parts.append(f"{field_name} <= %({p})s")
            params[p] = value
        elif op == 'between':
            p2 = f"{p}_2"
            where_parts.append(f"{field_name} BETWEEN %({p})s AND %({p2})s")
            params[p] = value
            params[p2] = value2
        elif op == 'is_null':
            where_parts.append(f"({field_name} IS NULL OR {field_name} = '')")
        elif op == 'not_null':
            where_parts.append(f"({field_name} IS NOT NULL AND {field_name} != '')")

    if not where_parts:
        return ""

    return "WHERE " + " AND ".join(where_parts)


def build_query(config, user_cfo=None):
    """
    Строит SQL для табличного отчёта.
    Возвращает (sql, params).
    """
    source = config.get('source')
    if source not in DATA_SOURCES:
        raise ReportBuilderError(f"Неизвестный источник: {source}")

    source_meta = DATA_SOURCES[source]
    params = {}

    columns = config.get('columns') or []
    if not columns:
        raise ReportBuilderError("Не выбрано ни одной колонки")

    select_parts = []
    group_by = []
    has_agg = False

    for col in columns:
        if isinstance(col, str):
            fmeta = _validate_field(source_meta, col)
            select_parts.append(col)
            group_by.append(col)
        elif isinstance(col, dict):
            field = col.get('field')
            agg = col.get('agg')
            alias = col.get('alias') or (f"{field}_{agg}" if agg else field)
            fmeta = _validate_field(source_meta, field)

            if agg:
                has_agg = True
                allowed_aggs = {a['value'] for a in
                                [{'value': 'sum'}, {'value': 'count'},
                                 {'value': 'avg'}, {'value': 'min'}, {'value': 'max'}]}
                if agg not in allowed_aggs:
                    raise ReportBuilderError(f"Недопустимая агрегация: {agg}")
                select_parts.append(f"{agg.upper()}({field}) AS {alias}")
            else:
                select_parts.append(f"{field} AS {alias}")
                group_by.append(field)
        else:
            raise ReportBuilderError("Некорректный формат колонки")

    where_sql = _build_where(source_meta, config.get('filters'), params, user_cfo)

    # GROUP BY — только если есть агрегаты и неагрегированные поля
    group_sql = ""
    if has_agg:
        non_agg_fields = []
        for col in columns:
            if isinstance(col, str):
                non_agg_fields.append(col)
            elif isinstance(col, dict) and not col.get('agg'):
                non_agg_fields.append(col.get('field'))
        if non_agg_fields:
            group_sql = "GROUP BY " + ", ".join(dict.fromkeys(non_agg_fields))

    # Сортировка
    order_sql = ""
    order = config.get('order') or []
    if order:
        parts = []
        aliases = {c.get('alias') for c in columns if isinstance(c, dict)}
        for o in order:
            f = o.get('field')
            d = (o.get('dir') or 'asc').lower()
            if d not in ('asc', 'desc'):
                d = 'asc'
            if f not in aliases:
                _validate_field(source_meta, f)
            parts.append(f"{f} {d}")
        if parts:
            order_sql = "ORDER BY " + ", ".join(parts)

    # Лимит
    limit = config.get('limit')
    try:
        limit = int(limit) if limit else None
    except (TypeError, ValueError):
        limit = None
    if limit and limit > 0:
        limit_sql = f"LIMIT {limit}"
    else:
        limit_sql = ""

    sql = f"""
        SELECT {', '.join(select_parts)}
        FROM {source}
        {where_sql}
        {group_sql}
        {order_sql}
        {limit_sql}
    """
    return sql, params


def build_kpi_query(config, user_cfo=None):
    """
    Строит SQL для KPI-отчёта.
    Ожидает: source, kpi_field (например, сумма_заявки), kpi_agg (sum/count/avg),
             kpi_filters (список фильтров).
    Возвращает (sql, params).
    """
    source = config.get('source')
    if source not in DATA_SOURCES:
        raise ReportBuilderError(f"Неизвестный источник: {source}")

    source_meta = DATA_SOURCES[source]
    params = {}

    field = config.get('kpi_field')
    agg = config.get('kpi_agg') or 'sum'

    if field:
        _validate_field(source_meta, field)
    else:
        # Если поле не задано — считаем COUNT(*)
        field = '*'
        agg = 'count'

    where_sql = _build_where(source_meta, config.get('kpi_filters'), params, user_cfo)

    sql = f"SELECT {agg.upper()}({field}) AS value FROM {source} {where_sql}"
    return sql, params