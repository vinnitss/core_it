"""
Маршруты справочника согласующих по проектам.
"""
import os
import tempfile

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify)
from flask_login import login_required, current_user

from modules.approvers.services import (
    list_projects, get_project, list_all_approvers, get_filter_options,
    create_project, update_project, delete_project,
    add_approver_to_stage, remove_approver_from_stage,
    import_approvers_from_excel,
)

approvers_bp = Blueprint(
    'approvers', __name__,
    template_folder='../../templates/approvers'
)


def _can_edit():
    """Может ли текущий пользователь редактировать справочник."""
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, 'is_admin', False):
        return True
    return bool(getattr(current_user, 'can_edit_approvers', False))


# ==================== СПИСОК ====================
@approvers_bp.route('/')
@login_required
def index():
    filters = {
        'search': request.args.get('search', '').strip() or None,
        'isd': request.args.get('isd', '').strip() or None,
        'platform': request.args.get('platform', '').strip() or None,
        'registry_type': request.args.get('registry_type', '').strip() or None,
        'approver_id': request.args.get('approver_id', type=int),
    }
    projects = list_projects(**filters)
    options = get_filter_options()
    all_approvers = list_all_approvers()

    return render_template('approvers/index.html',
                           projects=projects,
                           options=options,
                           all_approvers=all_approvers,
                           filters=filters,
                           can_edit=_can_edit())


# ==================== ДЕТАЛИ / РЕДАКТИРОВАНИЕ ====================
@approvers_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if not _can_edit():
        flash('Нет прав на редактирование справочника', 'danger')
        return redirect(url_for('approvers.index'))

    if request.method == 'POST':
        try:
            pid = create_project(
                isd=request.form.get('isd', '').strip(),
                project=request.form.get('project', '').strip(),
                platform=request.form.get('platform', '').strip(),
                registry_type=request.form.get('registry_type', '').strip(),
            )
            flash('Проект добавлен', 'success')
            return redirect(url_for('approvers.detail', project_id=pid))
        except Exception as e:
            flash(f'Ошибка: {str(e)[:200]}', 'danger')

    return render_template('approvers/detail.html',
                           project=None,
                           all_approvers=list_all_approvers(),
                           can_edit=True)


@approvers_bp.route('/<int:project_id>', methods=['GET', 'POST'])
@login_required
def detail(project_id):
    project = get_project(project_id)
    if not project:
        flash('Запись не найдена', 'danger')
        return redirect(url_for('approvers.index'))

    if request.method == 'POST' and _can_edit():
        try:
            update_project(
                project_id,
                isd=request.form.get('isd', '').strip(),
                project=request.form.get('project', '').strip(),
                platform=request.form.get('platform', '').strip(),
                registry_type=request.form.get('registry_type', '').strip(),
            )
            flash('Изменения сохранены', 'success')
            return redirect(url_for('approvers.detail', project_id=project_id))
        except Exception as e:
            flash(f'Ошибка: {str(e)[:200]}', 'danger')

    return render_template('approvers/detail.html',
                           project=project,
                           all_approvers=list_all_approvers(),
                           can_edit=_can_edit())


@approvers_bp.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def delete(project_id):
    if not _can_edit():
        return jsonify({'error': 'Нет прав'}), 403
    try:
        delete_project(project_id)
        flash('Проект удалён', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)[:200]}', 'danger')
    return redirect(url_for('approvers.index'))


# ==================== СОГЛАСУЮЩИЕ НА ЭТАПАХ ====================
@approvers_bp.route('/<int:project_id>/stage/<int:stage>/add', methods=['POST'])
@login_required
def stage_add(project_id, stage):
    if not _can_edit():
        return jsonify({'error': 'Нет прав'}), 403

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    organization = request.form.get('organization', '').strip()

    if not name:
        flash('Укажите имя согласующего', 'danger')
        return redirect(url_for('approvers.detail', project_id=project_id))

    try:
        add_approver_to_stage(project_id, stage, name, email, phone, organization)
        flash('Согласующий добавлен', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)[:200]}', 'danger')
    return redirect(url_for('approvers.detail', project_id=project_id))


@approvers_bp.route('/<int:project_id>/stage/<int:stage>/<int:approver_id>/remove',
                    methods=['POST'])
@login_required
def stage_remove(project_id, stage, approver_id):
    if not _can_edit():
        return jsonify({'error': 'Нет прав'}), 403
    try:
        remove_approver_from_stage(project_id, stage, approver_id)
        flash('Согласующий удалён', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)[:200]}', 'danger')
    return redirect(url_for('approvers.detail', project_id=project_id))


# ==================== ЗАГРУЗКА EXCEL ====================
@approvers_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if not _can_edit():
        flash('Нет прав на импорт', 'danger')
        return redirect(url_for('approvers.index'))

    result = None
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('Выберите файл', 'danger')
            return redirect(request.url)
        if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            flash('Поддерживается только Excel (.xlsx, .xls)', 'danger')
            return redirect(request.url)

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                file.save(tmp.name)
                path = tmp.name
            result = import_approvers_from_excel(path, replace=True)
            os.unlink(path)
            flash(
                f'Импорт завершён: проектов — {result["projects"]}, '
                f'согласующих — {result["approvers"]}, связей — {result["links"]}',
                'success'
            )
        except Exception as e:
            flash(f'Ошибка импорта: {str(e)[:300]}', 'danger')

    return render_template('approvers/upload.html', result=result)