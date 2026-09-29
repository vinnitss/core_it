import os
import tempfile

from flask import Blueprint, render_template, request, jsonify

from modules.import_data.import_logic import (
    load_and_clean_applications, group_applications, upsert_applications,
    load_and_clean_registers, upsert_registers
)
from modules.contracts.import_logic import load_and_clean_contracts, upsert_contracts
from modules.contracts.services import link_all_applications
from modules.debts.import_logic import import_debts
from modules.core.utils import engine, create_all_views

import_bp = Blueprint('import', __name__, template_folder='../../templates')


def _has_file(f):
    return f is not None and f.filename != ''


@import_bp.route('/', methods=['GET', 'POST'])
def import_page():
    result_messages = None
    result_error = None

    if request.method == 'POST':
        file_app = request.files.get('file_app')
        file_reg = request.files.get('file_reg')
        file_contracts = request.files.get('file_contracts')
        file_debts = request.files.get('file_debts')

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not (_has_file(file_app) or _has_file(file_reg) or
                _has_file(file_contracts) or _has_file(file_debts)):
            msg = 'Загрузите хотя бы один файл'
            if is_ajax:
                return jsonify({'success': False, 'error': msg})
            return render_template('import.html', result_error=msg)

        messages = []

        try:
            # --- Импорт заявок ---
            if _has_file(file_app):
                if not (file_app.filename.endswith('.xlsx') or file_app.filename.endswith('.xls')):
                    msg = 'Файл заявок должен быть Excel (.xlsx или .xls)'
                    if is_ajax:
                        return jsonify({'success': False, 'error': msg})
                    return render_template('import.html', result_error=msg)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    file_app.save(tmp.name)
                    app_path = tmp.name
                df_app_raw = load_and_clean_applications(app_path)
                df_app_clean = group_applications(df_app_raw)
                upsert_applications(df_app_clean)
                messages.append(f'заявок: {len(df_app_clean)}')
                os.unlink(app_path)

            # --- Импорт реестров ---
            if _has_file(file_reg):
                if not (file_reg.filename.endswith('.xlsx') or file_reg.filename.endswith('.xls')):
                    msg = 'Файл реестров должен быть Excel (.xlsx или .xls)'
                    if is_ajax:
                        return jsonify({'success': False, 'error': msg})
                    return render_template('import.html', result_error=msg)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    file_reg.save(tmp.name)
                    reg_path = tmp.name
                df_reg_clean = load_and_clean_registers(reg_path)
                upsert_registers(df_reg_clean)
                messages.append(f'реестров: {len(df_reg_clean)}')
                os.unlink(reg_path)

            # --- Импорт договоров ---
            if _has_file(file_contracts):
                if not (file_contracts.filename.endswith('.xlsx') or file_contracts.filename.endswith('.xls')):
                    msg = 'Файл договоров должен быть Excel (.xlsx или .xls)'
                    if is_ajax:
                        return jsonify({'success': False, 'error': msg})
                    return render_template('import.html', result_error=msg)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    file_contracts.save(tmp.name)
                    con_path = tmp.name
                df_contracts = load_and_clean_contracts(con_path)
                upsert_contracts(engine, df_contracts)
                messages.append(f'договоров: {len(df_contracts)}')
                os.unlink(con_path)
                link_all_applications()

            # --- Импорт задолженности ---
            if _has_file(file_debts):
                if not (file_debts.filename.endswith('.xlsx') or file_debts.filename.endswith('.xls')):
                    msg = 'Файл задолженности должен быть Excel (.xlsx или .xls)'
                    if is_ajax:
                        return jsonify({'success': False, 'error': msg})
                    return render_template('import.html', result_error=msg)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    file_debts.save(tmp.name)
                    deb_path = tmp.name
                deb_count = import_debts(deb_path)
                messages.append(f'задолженность: {deb_count}')
                os.unlink(deb_path)

            if _has_file(file_app) or _has_file(file_reg):
                create_all_views(engine)

            print('IMPORT RESULT:', messages, flush=True)

            if is_ajax:
                return jsonify({
                    'success': True,
                    'messages': messages,
                    'message': ', '.join(messages),
                })
            result_messages = messages

        except Exception as e:
            result_error = str(e)[:1000]
            print('IMPORT ERROR:', result_error, flush=True)
            if is_ajax:
                return jsonify({'success': False, 'error': result_error})

    return render_template('import.html',
                           result_messages=result_messages,
                           result_error=result_error)