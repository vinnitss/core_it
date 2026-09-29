from flask import Blueprint, render_template, request, send_file, redirect, url_for
from modules.debts.services import (
    get_debts_summary,
    get_reconciliation_table,
    get_debts_list,
)
from modules.core.utils import export_df_with_formatting
from modules.debts.services import get_contract_details

debts_bp = Blueprint('debts', __name__, template_folder='../../templates/debts')

@debts_bp.route('/')
def index():
    return redirect(url_for('contracts.index'))


@debts_bp.route('/contract/<contract_code>')
def contract_detail(contract_code):
    return redirect(url_for('contracts.detail', contract_code=contract_code))

@debts_bp.route('/export')
def export():
    df = get_debts_list(
        request.args.get('вид_задолженности') or None,
        request.args.get('договор_код') or None,
    )
    output = export_df_with_formatting(df, sheet_name='Задолженность')
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(output, download_name=f'debts_{timestamp}.xlsx', as_attachment=True)