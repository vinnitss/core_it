from flask import Blueprint, render_template, send_file, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from modules.dashboard.services import (
    get_dashboard_data, get_all_contracts_data,
    get_finance_dashboard_data, get_finance_filter_options,
    get_operations_dashboard_data, get_operations_filter_options,
    get_payments_dynamics, get_contracts_dashboard_data, get_contracts_filter_options,
    get_spending_analytics, get_contracts_portfolio,
)

from io import BytesIO
from datetime import datetime
import pandas as pd

dashboard_bp = Blueprint('dashboard', __name__, template_folder='../../templates/dashboard')

@dashboard_bp.route('/')
def dashboard():
    # Главный дашборд — теперь это дашборд договоров
    return redirect(url_for('dashboard.contracts'))

@dashboard_bp.route('/export')
def export_contracts():
    df = get_all_contracts_data()
    from modules.core.utils import export_df_with_formatting
    output = export_df_with_formatting(df, sheet_name='Договоры')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(output, download_name=f'contracts_{timestamp}.xlsx', as_attachment=True)

@dashboard_bp.route('/finance')
def finance():
    filters = {
        'period': request.args.get('period', 'year'),
        'проект': request.args.get('проект', ''),
        'контрагент': request.args.get('контрагент', ''),
    }
    data = get_finance_dashboard_data(filters)
    options = get_finance_filter_options()
    return render_template('dashboard/finance.html',
                           data=data, filters=filters, options=options)

@dashboard_bp.route('/operations')
def operations():
    filters = {
        'period': request.args.get('period', 'year'),
        'проект': request.args.get('проект', ''),
        'контрагент': request.args.get('контрагент', ''),
    }
    data = get_operations_dashboard_data(filters)
    options = get_operations_filter_options()
    return render_template('dashboard/operations.html',
                           data=data, filters=filters, options=options)

@dashboard_bp.route('/contracts')
def contracts():
    return redirect(url_for('contracts.index'))

@dashboard_bp.route('/payments')
def payments():
    period = request.args.get('period', 'year')
    if period not in ('week', 'month', 'quarter', 'year', 'all'):
        period = 'year'
    data = get_payments_dynamics(period)
    return render_template('dashboard/payments.html', data=data, period=period)

@dashboard_bp.route('/debts')
def debts_dashboard():
    from modules.debts.services import get_debts_summary
    data = get_debts_summary()
    return render_template('dashboard/debts.html', data=data)

@dashboard_bp.route('/spending')
def spending():
    period = request.args.get('period', '12m')
    if period not in ('6m', '12m', '24m', 'all'):
        period = '12m'
    data = get_spending_analytics(period)
    return render_template('dashboard/spending.html', data=data, period=period)

@dashboard_bp.route('/cashflow')
def cashflow():
    # Редирект со старого URL
    return redirect(url_for('dashboard.spending'))

@dashboard_bp.route('/portfolio')
def portfolio():
    data = get_contracts_portfolio()
    return render_template('dashboard/portfolio.html', data=data)


@dashboard_bp.route('/my')
@login_required
def my_dashboard():
    from modules.dashboard.user_dashboard import render_dashboard, get_available_widgets
    widgets = render_dashboard(current_user.id)
    available = get_available_widgets(current_user.id)
    return render_template('dashboard/my_dashboard.html',
                           widgets=widgets,
                           available=available)


@dashboard_bp.route('/api/widgets/add', methods=['POST'])
@login_required
def api_widget_add():
    from modules.dashboard.user_dashboard import add_widget
    data = request.get_json() or {}
    key = data.get('key')
    size = data.get('size')
    if not key:
        return jsonify({'error': 'no key'}), 400
    ok = add_widget(current_user.id, key, size)
    return jsonify({'ok': ok})


@dashboard_bp.route('/api/widgets/remove', methods=['POST'])
@login_required
def api_widget_remove():
    from modules.dashboard.user_dashboard import remove_widget
    data = request.get_json() or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'no key'}), 400
    remove_widget(current_user.id, key)
    return jsonify({'ok': True})


@dashboard_bp.route('/api/widgets/reorder', methods=['POST'])
@login_required
def api_widget_reorder():
    from modules.dashboard.user_dashboard import reorder_widgets
    data = request.get_json() or {}
    keys = data.get('keys') or []
    reorder_widgets(current_user.id, keys)
    return jsonify({'ok': True})


@dashboard_bp.route('/api/widgets/resize', methods=['POST'])
@login_required
def api_widget_resize():
    from modules.dashboard.user_dashboard import resize_widget
    data = request.get_json() or {}
    key = data.get('key')
    size = data.get('size')
    if not key or size not in ('small', 'medium', 'full'):
        return jsonify({'error': 'bad params'}), 400
    resize_widget(current_user.id, key, size)
    return jsonify({'ok': True})


@dashboard_bp.route('/api/widgets/reset', methods=['POST'])
@login_required
def api_widget_reset():
    from modules.dashboard.user_dashboard import set_default_dashboard
    set_default_dashboard(current_user.id, use_default=True)
    return jsonify({'ok': True})