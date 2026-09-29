from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from modules.contracts.services import (
    get_contracts_list, get_contracts_filter_options, get_contract_details,
)

contracts_bp = Blueprint(
    'contracts', __name__,
    template_folder='../../templates/contracts'
)


@contracts_bp.route('/')
@login_required
def index():
    filters = {
        'ответственный': request.args.get('ответственный', '').strip(),
        'flags': request.args.getlist('flag'),
        'payment_mode': request.args.get('payment_mode', '').strip() or None,
    }
    contracts = get_contracts_list(filters)
    options = get_contracts_filter_options()
    return render_template('contracts/index.html',
                           contracts=contracts,
                           options=options,
                           filters=filters)


@contracts_bp.route('/<contract_code>')
@login_required
def detail(contract_code):
    details = get_contract_details(contract_code)
    return render_template('contracts/detail.html', details=details)


# ==================== РЕДИРЕКТЫ СО СТАРЫХ URL ====================
@contracts_bp.route('/legacy/from-dashboard')
@login_required
def legacy_dashboard():
    return redirect(url_for('contracts.index'))


@contracts_bp.route('/legacy/from-debts')
@login_required
def legacy_debts():
    return redirect(url_for('contracts.index'))