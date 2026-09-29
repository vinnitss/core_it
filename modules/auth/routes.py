from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from modules.auth.services import (
    authenticate, verify_password_by_id, set_password,
    set_must_change_password,
)

auth_bp = Blueprint('auth', __name__, template_folder='../../templates/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home.index'))

    error = None
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = authenticate(email, password)
        if user is None:
            error = 'Неверный email или пароль'
        else:
            login_user(user, remember=False)
            if user.must_change_password:
                return redirect(url_for('auth.change_password'))
            next_url = request.args.get('next')
            return redirect(next_url or url_for('home.index'))

    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    error = None
    if request.method == 'POST':
        old = request.form.get('old_password') or ''
        new = request.form.get('new_password') or ''
        confirm = request.form.get('confirm_password') or ''

        if new != confirm:
            error = 'Пароли не совпадают'
        elif len(new) < 8:
            error = 'Пароль должен содержать не менее 8 символов'
        elif not verify_password_by_id(current_user.id, old):
            error = 'Неверный текущий пароль'
        else:
            set_password(current_user.id, new)
            set_must_change_password(current_user.id, False)
            flash('Пароль изменён', 'success')
            return redirect(url_for('home.index'))

    return render_template('auth/change_password.html', error=error)


@auth_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    from modules.auth.services import set_start_page
    from modules.core.sidebar import get_hidden_sections

    if request.method == 'POST':
        start_page = request.form.get('start_page', 'home')
        set_start_page(current_user.id, start_page)
        current_user.start_page = start_page
        flash('Настройки сохранены', 'success')
        return redirect(url_for('auth.settings'))

    return render_template('auth/settings.html',
                           hidden_sections=get_hidden_sections(current_user.id))