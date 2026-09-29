from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required

from modules.auth.services import (
    list_users, create_user, update_user, get_user_by_id,
    set_password, set_must_change_password,
)

admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')


def admin_required(f):
    """Декоратор: только для администраторов."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Доступ только для администраторов', 'danger')
            return redirect(url_for('home.index'))
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users_list = list_users()
    return render_template('admin/users.html', users=users_list)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    error = None
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        role = request.form.get('role') or 'viewer'
        department = (request.form.get('department') or '').strip() or None
        can_import = request.form.get('can_import') == 'on'
        can_edit_approvers = request.form.get('can_edit_approvers') == 'on'

        if not email or '@' not in email:
            error = 'Некорректный email'
        elif len(password) < 8:
            error = 'Пароль должен содержать не менее 8 символов'
        elif role not in ('admin', 'manager', 'viewer'):
            error = 'Некорректная роль'
        else:
            try:
                create_user(
                    email=email,
                    password=password,
                    role=role,
                    department=department,
                    can_import=can_import,
                    must_change_password=True,
                )
                flash(f'Пользователь {email} создан. При первом входе потребуется смена пароля.', 'success')
                return redirect(url_for('admin.users'))
            except ValueError as e:
                error = str(e)

    return render_template('admin/user_form.html',
                           mode='create',
                           user=None,
                           error=error)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('admin.users'))

    error = None
    if request.method == 'POST':
        role = request.form.get('role') or 'viewer'
        department = (request.form.get('department') or '').strip() or None
        can_import = request.form.get('can_import') == 'on'
        is_active = request.form.get('is_active') == 'on'
        can_edit_approvers = request.form.get('can_edit_approvers') == 'on'

        if role not in ('admin', 'manager', 'viewer'):
            error = 'Некорректная роль'
        elif user_id == current_user.id and not is_active:
            error = 'Нельзя деактивировать самого себя'
        elif user_id == current_user.id and role != 'admin':
            error = 'Нельзя снять с себя роль администратора'
        else:
            update_user(user_id,
                        role=role,
                        department=department,
                        can_import=can_import,
                        is_active=is_active)
            flash('Изменения сохранены', 'success')
            return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html',
                           mode='edit',
                           user=user,
                           error=error)


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def user_reset_password(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('admin.users'))

    new_password = request.form.get('new_password') or ''
    if len(new_password) < 8:
        flash('Пароль должен содержать не менее 8 символов', 'danger')
        return redirect(url_for('admin.users'))

    set_password(user_id, new_password)
    set_must_change_password(user_id, True)
    flash(f'Пароль для {user.email} сброшен. При следующем входе потребуется смена.', 'success')
    return redirect(url_for('admin.users'))