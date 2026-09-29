"""
Маршруты конструктора отчётов.
- /builder/            — редактор отчёта
- /builder/list        — список сохранённых
- /builder/<id>/view   — просмотр сохранённого
- /builder/api/run     — выполнить (без сохранения)
- /builder/api/save    — сохранить
- /builder/api/<id>/delete — удалить
- /builder/<id>/export — экспорт в Excel
"""
from io import BytesIO
from datetime import datetime

import pandas as pd
from flask import (Blueprint, render_template, request, jsonify,
                   redirect, url_for, flash, send_file, abort)
from flask_login import login_required, current_user

from modules.report_builder.builder import (
    build_query, build_kpi_query, ReportBuilderError,
)
from modules.report_builder.meta import DATA_SOURCES, OPERATORS, AGGREGATIONS
from modules.report_builder.services import (
    create_report, update_report, delete_report, get_report, list_reports,
)
from modules.core.utils import engine, current_cfo, export_df_with_formatting, read_sql

report_builder_bp = Blueprint(
    'report_builder', __name__, template_folder='../../templates/builder'
)


# ==================== ВСПОМОГАТЕЛЬНОЕ ====================
def _run_config(config):
    """Выполняет конфиг, возвращает (columns, data, error)."""
    cfo = current_cfo()
    report_type = config.get('report_type', 'table')

    try:
        if report_type == 'kpi':
            sql, params = build_kpi_query(config, user_cfo=cfo)
            df = read_sql(sql, engine, params=params)
            value = df.iloc[0, 0] if not df.empty else 0
            return ['Значение'], [{'Значение': float(value) if value is not None else 0}], None
        else:
            sql, params = build_query(config, user_cfo=cfo)
            df = read_sql(sql, engine, params=params)
            return df.columns.tolist(), df.to_dict('records'), None
    except ReportBuilderError as e:
        return [], [], str(e)
    except Exception as e:
        return [], [], f'Ошибка выполнения: {str(e)[:400]}'


def _can_edit(report):
    """Может ли текущий пользователь редактировать отчёт."""
    if not report:
        return False
    if current_user.is_admin:
        return True
    return report['owner_id'] == current_user.id and not report['is_system']


# ==================== СТРАНИЦЫ ====================
@report_builder_bp.route('/')
@login_required
def index():
    report_id = request.args.get('id', type=int)
    report = None
    if report_id:
        report = get_report(report_id)
        if not report:
            flash('Отчёт не найден', 'danger')
            return redirect(url_for('report_builder.index'))

    return render_template(
        'builder/index.html',
        sources=DATA_SOURCES,
        operators=OPERATORS,
        aggregations=AGGREGATIONS,
        report=report,
    )


@report_builder_bp.route('/list')
@login_required
def list_page():
    mine_only = request.args.get('mine') == '1'
    reports = list_reports(
        user_id=current_user.id,
        include_public=True,
        include_system=True,
        only_mine=mine_only,
    )
    return render_template('builder/list.html',
                           reports=reports,
                           mine_only=mine_only)


@report_builder_bp.route('/<int:report_id>/view')
@login_required
def view_report(report_id):
    report = get_report(report_id)
    if not report:
        abort(404)

    # Проверка доступа: админ, владелец, публичный или системный
    if not (current_user.is_admin
            or report['owner_id'] == current_user.id
            or report['is_public']
            or report['is_system']):
        abort(403)

    columns, data, error = _run_config(report['config'])
    return render_template(
        'builder/view.html',
        report=report,
        columns=columns,
        data=data,
        error=error,
        can_edit=_can_edit(report),
    )


# ==================== API ====================
@report_builder_bp.route('/api/run', methods=['POST'])
@login_required
def api_run():
    config = request.get_json() or {}
    columns, data, error = _run_config(config)
    if error:
        return jsonify({'error': error}), 400
    return jsonify({
        'columns': columns,
        'data': data,
        'count': len(data),
    })


@report_builder_bp.route('/api/save', methods=['POST'])
@login_required
def api_save():
    payload = request.get_json() or {}
    config = payload.get('config') or {}
    report_id = payload.get('id')

    name = (payload.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Укажите название отчёта'}), 400

    description = (payload.get('description') or '').strip()
    is_public = bool(payload.get('is_public'))
    report_type = config.get('report_type', 'table')

    try:
        if report_id:
            report = get_report(int(report_id))
            if not _can_edit(report):
                return jsonify({'error': 'Нет прав на изменение отчёта'}), 403
            update_report(
                int(report_id),
                name=name,
                description=description,
                config=config,
                is_public=is_public,
            )
            return jsonify({'id': int(report_id), 'action': 'updated'})
        else:
            new_id = create_report(
                name=name,
                description=description,
                report_type=report_type,
                config=config,
                owner_id=current_user.id,
                is_public=is_public,
            )
            return jsonify({'id': new_id, 'action': 'created'})
    except Exception as e:
        return jsonify({'error': str(e)[:400]}), 500


@report_builder_bp.route('/api/<int:report_id>/delete', methods=['POST'])
@login_required
def api_delete(report_id):
    report = get_report(report_id)
    if not report:
        return jsonify({'error': 'Отчёт не найден'}), 404
    if not _can_edit(report):
        return jsonify({'error': 'Нет прав на удаление'}), 403
    delete_report(report_id)
    return jsonify({'ok': True})


@report_builder_bp.route('/<int:report_id>/export')
@login_required
def export_report(report_id):
    report = get_report(report_id)
    if not report:
        abort(404)
    if not (current_user.is_admin
            or report['owner_id'] == current_user.id
            or report['is_public']
            or report['is_system']):
        abort(403)

    columns, data, error = _run_config(report['config'])
    if error or not data:
        flash(f'Нечего экспортировать: {error or "нет данных"}', 'warning')
        return redirect(url_for('report_builder.view_report', report_id=report_id))

    df = pd.DataFrame(data)
    output = export_df_with_formatting(df, sheet_name=report['name'][:30])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = ''.join(c for c in report['name'] if c.isalnum() or c in '-_')[:40] or 'report'
    return send_file(
        output,
        download_name=f'{safe_name}_{timestamp}.xlsx',
        as_attachment=True,
    )