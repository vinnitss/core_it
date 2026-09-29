"""
API для управления sidebar.
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from modules.core.sidebar import (
    pin_section, unpin_section, hide_section, reset_sidebar,
)

sidebar_bp = Blueprint('sidebar', __name__)


@sidebar_bp.route('/pin', methods=['POST'])
@login_required
def api_pin():
    data = request.get_json() or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'no key'}), 400
    ok = pin_section(current_user.id, key)
    return jsonify({'ok': ok})


@sidebar_bp.route('/unpin', methods=['POST'])
@login_required
def api_unpin():
    data = request.get_json() or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'no key'}), 400
    ok = unpin_section(current_user.id, key)
    return jsonify({'ok': ok})


@sidebar_bp.route('/hide', methods=['POST'])
@login_required
def api_hide():
    data = request.get_json() or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'no key'}), 400
    ok = hide_section(current_user.id, key)
    return jsonify({'ok': ok})


@sidebar_bp.route('/reset', methods=['POST'])
@login_required
def api_reset():
    reset_sidebar(current_user.id)
    return jsonify({'ok': True})


@sidebar_bp.route('/unhide', methods=['POST'])
@login_required
def api_unhide():
    from modules.core.sidebar import unhide_section
    data = request.get_json() or {}
    key = data.get('key')
    if not key:
        return jsonify({'error': 'no key'}), 400
    ok = unhide_section(current_user.id, key)
    return jsonify({'ok': ok})