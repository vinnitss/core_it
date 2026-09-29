"""
Сервис для работы с персональным дашбордом пользователя.
"""
import json

import pandas as pd
from sqlalchemy import text

from modules.core.utils import engine
from modules.dashboard.widgets import WIDGETS, render_widget


# Дефолтный набор виджетов для нового пользователя
DEFAULT_WIDGETS = [
    {'key': 'kpi_kz', 'size': 'small'},
    {'key': 'kpi_apps', 'size': 'small'},
    {'key': 'kpi_expiring', 'size': 'small'},
    {'key': 'kpi_mismatch', 'size': 'small'},
    {'key': 'chart_payments', 'size': 'full'},
    {'key': 'table_reconciliation', 'size': 'full'},
]


def get_user_dashboard(user_id):
    """Возвращает список виджетов пользователя. Если нет — создаёт дефолтный."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT widgets FROM user_dashboards WHERE user_id = :uid
        """), {'uid': user_id}).fetchone()

    if not row:
        # Создаём дефолтный
        save_user_dashboard(user_id, DEFAULT_WIDGETS)
        return DEFAULT_WIDGETS

    widgets = row[0]
    if isinstance(widgets, str):
        try:
            widgets = json.loads(widgets)
        except Exception:
            widgets = DEFAULT_WIDGETS

    # Отфильтровываем несуществующие виджеты
    widgets = [w for w in widgets if w.get('key') in WIDGETS]
    return widgets


def save_user_dashboard(user_id, widgets):
    """Сохраняет список виджетов пользователя."""
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO user_dashboards (user_id, widgets, updated_at)
            VALUES (:uid, CAST(:w AS jsonb), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET widgets = EXCLUDED.widgets,
                updated_at = NOW()
        """), {
            'uid': user_id,
            'w': json.dumps(widgets, ensure_ascii=False),
        })
        conn.commit()


def add_widget(user_id, widget_key, size=None):
    """Добавляет виджет в конец дашборда."""
    if widget_key not in WIDGETS:
        return False
    widgets = get_user_dashboard(user_id)
    if any(w['key'] == widget_key for w in widgets):
        return False  # уже есть
    meta = WIDGETS[widget_key]
    widgets.append({
        'key': widget_key,
        'size': size or meta.get('default_size', 'medium'),
    })
    save_user_dashboard(user_id, widgets)
    return True


def remove_widget(user_id, widget_key):
    """Удаляет виджет."""
    widgets = get_user_dashboard(user_id)
    widgets = [w for w in widgets if w['key'] != widget_key]
    save_user_dashboard(user_id, widgets)


def reorder_widgets(user_id, ordered_keys):
    """Меняет порядок виджетов."""
    widgets = get_user_dashboard(user_id)
    by_key = {w['key']: w for w in widgets}
    new_widgets = [by_key[k] for k in ordered_keys if k in by_key]
    # Добавляем виджеты, которых не было в ordered_keys (не должны теряться)
    for w in widgets:
        if w['key'] not in ordered_keys:
            new_widgets.append(w)
    save_user_dashboard(user_id, new_widgets)


def resize_widget(user_id, widget_key, new_size):
    """Меняет размер виджета: small / medium / full."""
    if new_size not in ('small', 'medium', 'full'):
        return
    widgets = get_user_dashboard(user_id)
    for w in widgets:
        if w['key'] == widget_key:
            w['size'] = new_size
            break
    save_user_dashboard(user_id, widgets)


def render_dashboard(user_id):
    """
    Возвращает список словарей:
      {key, size, meta, data}
    для рендера на странице.
    """
    widgets = get_user_dashboard(user_id)
    result = []
    for w in widgets:
        key = w['key']
        if key not in WIDGETS:
            continue
        meta = WIDGETS[key]
        data = render_widget(key)
        result.append({
            'key': key,
            'size': w.get('size', meta.get('default_size', 'medium')),
            'meta': meta,
            'data': data,
        })
    return result


def get_available_widgets(user_id):
    """Возвращает виджеты, доступные для добавления, по категориям."""
    current = {w['key'] for w in get_user_dashboard(user_id)}
    by_cat = {}
    for key, meta in WIDGETS.items():
        if key in current:
            continue
        cat = meta.get('category', 'Прочее')
        by_cat.setdefault(cat, []).append({
            'key': key,
            'name': meta['name'],
            'type': meta['type'],
            'default_size': meta.get('default_size', 'medium'),
        })
    return by_cat


def set_default_dashboard(user_id, use_default=True):
    """Сбрасывает на дефолтный набор виджетов."""
    if use_default:
        save_user_dashboard(user_id, DEFAULT_WIDGETS)
    else:
        save_user_dashboard(user_id, [])