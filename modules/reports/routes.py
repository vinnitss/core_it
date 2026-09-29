from flask import Blueprint, render_template, request, send_file, jsonify
from modules.reports.services import get_data, get_filter_options
from modules.core.utils import engine, read_sql
import pandas as pd
from io import BytesIO
from datetime import datetime

reports_bp = Blueprint('reports', __name__, template_folder='../../templates/reports')

@reports_bp.route('/')
def index():
    """Отчёт по реестровым заявкам (pay_cal)."""
    df = get_data('pay_cal', None)
    data = df.to_dict('records')
    return render_template('reports/index.html', data=data)

@reports_bp.route('/export')
def export():
    view = request.args.get('view', 'quick')
    filters = {
        'проект': request.args.get('проект'),
        'контрагент': request.args.get('контрагент'),
        'статус_реестра': request.args.get('статус_реестра'),
        'статус_согласования': request.args.get('статус_согласования'),
        'оплачена': request.args.get('оплачена'),
        'дата_от': request.args.get('дата_от'),
        'дата_до': request.args.get('дата_до')
    }
    df = get_data(view, filters)
    from modules.core.utils import export_df_with_formatting
    output = export_df_with_formatting(df, sheet_name='Отчёт')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(output, download_name=f'report_{view}_{timestamp}.xlsx', as_attachment=True)

@reports_bp.route('/api/registers')
def api_registers():
    draw = int(request.args.get('draw', 1))
    start = int(request.args.get('start', 0))
    length = int(request.args.get('length', 25))
    search_value = request.args.get('search[value]', '')
    статус_реестра = request.args.get('статус_реестра', '')
    дата_от = request.args.get('дата_от', '')
    дата_до = request.args.get('дата_до', '')

    if статус_реестра in ('None', ''):
        статус_реестра = None
    if дата_от in ('None', ''):
        дата_от = None
    if дата_до in ('None', ''):
        дата_до = None

    where_clauses = []
    params = {}
    if статус_реестра:
        where_clauses.append("вычисленный_статус = %(статус_реестра)s")
        params['статус_реестра'] = статус_реестра
    if дата_от and дата_до:
        where_clauses.append("дата_реестра BETWEEN %(дата_от)s AND %(дата_до)s")
        params['дата_от'] = дата_от
        params['дата_до'] = дата_до
    elif дата_от:
        where_clauses.append("дата_реестра >= %(дата_от)s")
        params['дата_от'] = дата_от
    elif дата_до:
        where_clauses.append("дата_реестра <= %(дата_до)s")
        params['дата_до'] = дата_до
    if search_value:
        search_clause = """
            (номер_реестра::text ILIKE %(search)s OR
             статус ILIKE %(search)s OR
             дополнительный_статус ILIKE %(search)s OR
             вычисленный_статус ILIKE %(search)s)
        """
        where_clauses.append(search_clause)
        params['search'] = f'%{search_value}%'

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    count_sql = f"SELECT COUNT(*) FROM v_registers {where_sql}"
    total_filtered = int(read_sql(count_sql, engine, params=params).iloc[0, 0])
    total_records = int(read_sql("SELECT COUNT(*) FROM v_registers", engine).iloc[0, 0])

    data_sql = f"""
        SELECT номер_реестра, сумма_согласованная, вычисленный_статус, дата_реестра, статус, дополнительный_статус
        FROM v_registers
        {where_sql}
        ORDER BY дата_реестра DESC, номер_реестра DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """
    params['limit'] = length
    params['offset'] = start
    df = read_sql(data_sql, engine, params=params)

    # Преобразуем даты в строки, если есть
    if 'дата_реестра' in df.columns:
        df['дата_реестра'] = df['дата_реестра'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')

    # Конвертируем все numpy-типы в стандартные Python-типы
    data = []
    for record in df.to_dict('records'):
        clean_record = {}
        for key, value in record.items():
            if hasattr(value, 'item'):   # numpy scalar
                clean_record[key] = value.item()
            elif isinstance(value, float):
                clean_record[key] = float(value)
            elif isinstance(value, int):
                clean_record[key] = int(value)
            else:
                clean_record[key] = value
        data.append(clean_record)

    return {
        'draw': draw,
        'recordsTotal': total_records,
        'recordsFiltered': total_filtered,
        'data': data
    }
