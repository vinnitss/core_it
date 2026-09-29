import os
import tempfile

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from modules.objects.services import (
    import_objects_from_csv, generate_missing_codes,
    get_objects, get_object_filter_options,
    get_object_by_id, get_objects_for_map, rebuild_object_tokens, get_tokens,
)

from modules.objects.matching import (
    get_match_review, update_application_match, save_matches, clear_matches,
)

objects_bp = Blueprint('objects', __name__, template_folder='../../templates/objects')

@objects_bp.route('/tokens')
@login_required
def tokens():
    if not current_user.is_admin:
        flash('Доступ только для администраторов', 'danger')
        return redirect(url_for('home.index'))

    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 100))
    min_occ = int(request.args.get('min_occurrences', 5))
    search = request.args.get('search', '').strip() or None

    data = get_tokens(page=page, per_page=per_page, min_occurrences=min_occ, search=search)
    return render_template('objects/tokens.html', data=data,
                           min_occurrences=min_occ, search=search or '')


@objects_bp.route('/tokens/rebuild', methods=['POST'])
@login_required
def tokens_rebuild():
    if not current_user.is_admin:
        flash('Доступ только для администраторов', 'danger')
        return redirect(url_for('home.index'))

    try:
        count = rebuild_object_tokens()
        flash(f'Токенизация завершена: извлечено {count} уникальных токенов', 'success')
    except Exception as e:
        flash(f'Ошибка токенизации: {str(e)[:300]}', 'danger')
    return redirect(url_for('objects.tokens'))


@objects_bp.route('/')
@login_required
def index():
    """Список объектов."""
    filters = {
        'project': request.args.get('project', '').strip() or None,
        'otype': request.args.get('type', '').strip() or None,
        'status': request.args.get('status', '').strip() or None,
        'search': request.args.get('search', '').strip() or None,
    }
    objects = get_objects(**filters)
    options = get_object_filter_options()
    # Переименовываем для шаблона обратно в type
    template_filters = {
        'project': filters['project'],
        'type': filters['otype'],
        'status': filters['status'],
        'search': filters['search'],
    }
    return render_template('objects/index.html',
                           objects=objects,
                           options=options,
                           filters=template_filters)


@objects_bp.route('/map')
@login_required
def map_view():
    """Карта объектов."""
    filters = {
        'project': request.args.get('project', '').strip() or None,
        'otype': request.args.get('type', '').strip() or None,
        'status': request.args.get('status', '').strip() or None,
    }
    points = get_objects_for_map(**filters)
    options = get_object_filter_options()
    template_filters = {
        'project': filters['project'],
        'type': filters['otype'],
        'status': filters['status'],
    }
    return render_template('objects/map.html',
                           points=points,
                           options=options,
                           filters=template_filters)


@objects_bp.route('/<int:obj_id>')
@login_required
def detail(obj_id):
    """Карточка объекта."""
    obj = get_object_by_id(obj_id)
    if not obj:
        flash('Объект не найден', 'danger')
        return redirect(url_for('objects.index'))
    return render_template('objects/detail.html', obj=obj)


@objects_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Загрузка CSV со списком объектов."""
    if not current_user.is_admin:
        flash('Доступ только для администраторов', 'danger')
        return redirect(url_for('objects.index'))

    result = None
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('Выберите файл', 'danger')
            return redirect(request.url)
        if not file.filename.endswith('.csv'):
            flash('Поддерживается только формат CSV', 'danger')
            return redirect(request.url)

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                file.save(tmp.name)
                path = tmp.name
            added, updated, total = import_objects_from_csv(path)
            os.unlink(path)
            result = {'added': added, 'updated': updated, 'total': total}
            flash(f'Импорт завершён: добавлено {added}, обновлено {updated}', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {str(e)[:300]}', 'danger')

    return render_template('objects/upload.html', result=result)

@objects_bp.route('/generate-codes', methods=['POST'])
@login_required
def generate_codes():
    """Присвоить коды объектам без кода."""
    if not current_user.is_admin:
        flash('Доступ только для администраторов', 'danger')
        return redirect(url_for('objects.index'))

    try:
        count = generate_missing_codes()
        flash(f'Коды присвоены {count} объектам', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)[:300]}', 'danger')
    return redirect(url_for('objects.index'))

@objects_bp.route('/match-review')
@login_required
def match_review():
    """Список заявок с сохранёнными матчами."""
    filters = {
        'confidence': request.args.get('confidence', '').strip() or None,
        'project': request.args.get('project', '').strip() or None,
        'search': request.args.get('search', '').strip() or None,
        'only_unconfirmed': request.args.get('only_unconfirmed') == '1',
    }
    page = int(request.args.get('page', 1))
    data = get_match_review(page=page, per_page=50, **filters)
    options = get_object_filter_options()

    from modules.core.utils import engine, read_sql
    import pandas as pd
    stats = read_sql("""
        SELECT 
            object_match_confidence,
            count(*) AS cnt,
            count(*) FILTER (WHERE object_id IS NOT NULL) AS assigned
        FROM applications
        WHERE object_match_confidence IS NOT NULL
        GROUP BY object_match_confidence
    """, engine).to_dict('records')

    return render_template('objects/match_review.html',
                           data=data,
                           options=options,
                           filters=filters,
                           stats=stats)

@objects_bp.route('/match-detail', methods=['GET', 'POST'])
@login_required
def match_detail():
    """Карточка одной заявки для ручного разбора матча."""
    from modules.core.utils import engine, read_sql
    import pandas as pd
    import json

    app_num = request.args.get('num')
    app_date = request.args.get('date')

    if not app_num or not app_date:
        flash('Не указана заявка', 'danger')
        return redirect(url_for('objects.match_review'))

    app_row = read_sql("""
        SELECT номер_заявки, дата, сумма_заявки, контрагент, проект,
               назначение_платежа, договор_контрагента, ответственный,
               object_id, object_match_confidence, object_match_candidates
        FROM applications
        WHERE номер_заявки = %(num)s AND дата = %(dt)s::date
    """, engine, params={'num': app_num, 'dt': app_date})

    if app_row.empty:
        flash('Заявка не найдена', 'danger')
        return redirect(url_for('objects.match_review'))

    application = app_row.to_dict('records')[0]

    candidates = []
    try:
        if application.get('object_match_candidates'):
            raw = application['object_match_candidates']
            if isinstance(raw, str):
                candidates = json.loads(raw)
            else:
                candidates = raw
    except Exception:
        candidates = []

    current_object = None
    if application.get('object_id'):
        current_object = get_object_by_id(int(application['object_id']))

    all_objects = get_objects()

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'confirm':
                oid = application.get('object_id')
                if not oid:
                    flash('Нет текущего объекта для подтверждения', 'warning')
                else:
                    update_application_match(app_num, app_date, object_id=int(oid), action='confirm')
                    flash('Матч подтверждён', 'success')
            elif action == 'reject':
                update_application_match(app_num, app_date, action='reject')
                flash('Матч отклонён', 'success')
            elif action == 'set':
                oid = request.form.get('object_id')
                if oid:
                    update_application_match(app_num, app_date, object_id=int(oid), action='set')
                    flash('Объект изменён', 'success')
                else:
                    flash('Не выбран объект', 'warning')
            elif action == 'next':
                return redirect(url_for('objects.match_review', only_unconfirmed='1'))
        except Exception as e:
            flash(f'Ошибка: {str(e)[:200]}', 'danger')

        return redirect(url_for('objects.match_detail', num=app_num, date=app_date))

    return render_template('objects/match_detail.html',
                           application=application,
                           candidates=candidates,
                           current_object=current_object,
                           all_objects=all_objects)


@objects_bp.route('/match-review/rebuild', methods=['POST'])
@login_required
def match_rebuild():
    """Пересчитать все матчи и сохранить."""
    if not current_user.is_admin:
        flash('Доступ только для администраторов', 'danger')
        return redirect(url_for('objects.match_review'))

    try:
        result = save_matches()
        flash(f'Матчи пересчитаны: {result["saved"]} заявок обработано', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)[:300]}', 'danger')
    return redirect(url_for('objects.match_review'))