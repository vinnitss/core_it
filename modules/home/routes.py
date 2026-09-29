from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from modules.home.services import get_home_data

home_bp = Blueprint('home', __name__, template_folder='../../templates/home')


@home_bp.route('/')
@login_required
def index():
    from flask_login import current_user
    if getattr(current_user, 'start_page', 'home') == 'my_dashboard':
        return redirect(url_for('dashboard.my_dashboard'))
    data = get_home_data()
    return render_template('home/index.html', data=data)