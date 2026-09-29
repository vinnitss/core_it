import os
from datetime import datetime, timedelta

from flask import Flask, redirect, url_for, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from modules.core.logging_config import setup_logging
from modules.core.utils import engine, create_all_tables, create_all_views

# Логирование — до всего остального
setup_logging()

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH

# Сессии
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=Config.SESSION_LIFETIME_HOURS)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE

# За Nginx
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Инициализация БД
with app.app_context():
    create_all_tables(engine)
    create_all_views(engine)

# Flask-Login
from flask_login import LoginManager, current_user

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Пожалуйста, войдите в систему'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    from modules.auth.services import get_user_by_id
    return get_user_by_id(user_id)


# Регистрация Blueprints
from modules.admin.routes import admin_bp
from modules.auth.routes import auth_bp
from modules.debts.routes import debts_bp
from modules.contracts.routes import contracts_bp
from modules.dashboard.routes import dashboard_bp
from modules.import_data.routes import import_bp
from modules.help.routes import help_bp
from modules.home.routes import home_bp
from modules.reports.routes import reports_bp
from modules.report_builder.routes import report_builder_bp
from modules.objects.routes import objects_bp
from modules.core.sidebar_routes import sidebar_bp
from modules.approvers.routes import approvers_bp

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(home_bp, url_prefix='/')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(import_bp, url_prefix='/import')
app.register_blueprint(debts_bp, url_prefix='/debts')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(objects_bp, url_prefix='/objects')
app.register_blueprint(help_bp, url_prefix='/help')
app.register_blueprint(report_builder_bp, url_prefix='/builder')
app.register_blueprint(contracts_bp, url_prefix='/contracts')
app.register_blueprint(sidebar_bp, url_prefix='/api/sidebar')
app.register_blueprint(approvers_bp, url_prefix='/approvers')

# Глобальная защита: всё, кроме логина, статики и /health, требует авторизации
@app.before_request
def require_login():
    allowed_endpoints = {'auth.login', 'static', 'health'}
    if request.endpoint in allowed_endpoints:
        return
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))


@app.context_processor
def inject_globals():
    """Добавляет в контекст шаблонов общие переменные и структуру sidebar."""
    from modules.core.sidebar import build_sidebar

    sidebar = {'main': [], 'hidden': [], 'service': [], 'admin': []}
    if current_user.is_authenticated:
        try:
            sidebar = build_sidebar(
                current_user.id,
                is_admin=getattr(current_user, 'is_admin', False),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Sidebar error: {e}")

    return {
        'current_year': datetime.now().year,
        'current_date': datetime.now().strftime('%d.%m.%Y'),
        'sidebar': sidebar,
    }


@app.route('/health')
def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)