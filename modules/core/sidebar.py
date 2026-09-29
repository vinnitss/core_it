"""
Сервис управления боковым меню.
Определяет список разделов, работу с закреплёнными/скрытыми.
"""
import json
import logging

from sqlalchemy import text

from modules.core.utils import engine

logger = logging.getLogger(__name__)


# ==================== РЕЕСТР РАЗДЕЛОВ ====================
# key: уникальный идентификатор
# name: отображаемое название
# icon: класс FontAwesome
# endpoint: имя Flask-эндпоинта для url_for
# fixed: если True — нельзя скрыть и всегда на месте
# admin_only: если True — показывается только админам
SECTIONS = {
    # --- Фиксированные ---
    'home': {
        'name': 'Главная',
        'icon': 'fa-home',
        'endpoint': 'home.index',
        'fixed': True,
    },
    'my_dashboard': {
        'name': 'Мой дашборд',
        'icon': 'fa-th-large',
        'endpoint': 'dashboard.my_dashboard',
        'fixed': True,
    },
    'reports': {
        'name': 'Быстрый отчёт',
        'icon': 'fa-bolt',
        'endpoint': 'reports.index',
        'fixed': True,
    },
    'contracts': {
        'name': 'Договоры и расчёты',
        'icon': 'fa-file-contract',
        'endpoint': 'contracts.index',
        'fixed': True,
    },
    'portfolio': {
        'name': 'Портфель договоров',
        'icon': 'fa-briefcase',
        'endpoint': 'dashboard.portfolio',
        'fixed': True,
    },
    'objects': {
        'name': 'Объекты',
        'icon': 'fa-map-marked-alt',
        'endpoint': 'objects.index',
        'fixed': True,
    },
        'approvers': {
        'name': 'Согласующие',
        'icon': 'fa-user-check',
        'endpoint': 'approvers.index',
        'fixed': False,   # опциональный — можно закрепить
    },

    # --- Опциональные ---
    'finance': {
        'name': 'Финансы',
        'icon': 'fa-chart-line',
        'endpoint': 'dashboard.finance',
    },
    'operations': {
        'name': 'Операции',
        'icon': 'fa-tasks',
        'endpoint': 'dashboard.operations',
    },
    'payments': {
        'name': 'Динамика оплат',
        'icon': 'fa-money-check-alt',
        'endpoint': 'dashboard.payments',
    },
    'spending': {
        'name': 'Средние расходы',
        'icon': 'fa-coins',
        'endpoint': 'dashboard.spending',
    },
    'builder': {
        'name': 'Конструктор',
        'icon': 'fa-tools',
        'endpoint': 'report_builder.list_page',
    },

    # --- Служебные (внизу) ---
    'import': {
        'name': 'Импорт',
        'icon': 'fa-cloud-upload-alt',
        'endpoint': 'import.import_page',
        'fixed': True,
        'group': 'service',
    },
    'help': {
        'name': 'Справка',
        'icon': 'fa-question-circle',
        'endpoint': 'help.index',
        'fixed': True,
        'group': 'service',
    },
    'settings': {
        'name': 'Настройки',
        'icon': 'fa-cog',
        'endpoint': 'auth.settings',
        'fixed': True,
        'group': 'service',
    },

    # --- Админские ---
    'admin_users': {
        'name': 'Пользователи',
        'icon': 'fa-users-cog',
        'endpoint': 'admin.users',
        'admin_only': True,
        'group': 'admin',
    },
    'objects_tokens': {
        'name': 'Токены объектов',
        'icon': 'fa-tags',
        'endpoint': 'objects.tokens',
        'admin_only': True,
        'group': 'admin',
    },
    'match_review': {
        'name': 'Проверка матчей',
        'icon': 'fa-crosshairs',
        'endpoint': 'objects.match_review',
        'admin_only': True,
        'group': 'admin',
    },
}


# ==================== ЧТЕНИЕ / ЗАПИСЬ ====================
def _default_settings():
    return {'pinned': [], 'hidden': []}


def get_user_sidebar(user_id):
    """Возвращает {'pinned': [...], 'hidden': [...]}."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT pinned_sections, hidden_sections
            FROM user_sidebar WHERE user_id = :uid
        """), {'uid': user_id}).fetchone()

    if not row:
        return _default_settings()

    def parse(v):
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return list(v)

    return {
        'pinned': parse(row[0]),
        'hidden': parse(row[1]),
    }


def save_user_sidebar(user_id, pinned, hidden):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO user_sidebar (user_id, pinned_sections, hidden_sections, updated_at)
            VALUES (:uid, CAST(:p AS jsonb), CAST(:h AS jsonb), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET pinned_sections = EXCLUDED.pinned_sections,
                hidden_sections = EXCLUDED.hidden_sections,
                updated_at = NOW()
        """), {
            'uid': user_id,
            'p': json.dumps(pinned, ensure_ascii=False),
            'h': json.dumps(hidden, ensure_ascii=False),
        })
        conn.commit()


# ==================== ОПЕРАЦИИ ====================
def pin_section(user_id, key):
    if key not in SECTIONS or SECTIONS[key].get('fixed'):
        return False
    s = get_user_sidebar(user_id)
    if key not in s['pinned']:
        s['pinned'].append(key)
    if key in s['hidden']:
        s['hidden'].remove(key)
    save_user_sidebar(user_id, s['pinned'], s['hidden'])
    return True


def unpin_section(user_id, key):
    s = get_user_sidebar(user_id)
    if key in s['pinned']:
        s['pinned'].remove(key)
    save_user_sidebar(user_id, s['pinned'], s['hidden'])
    return True


def hide_section(user_id, key):
    if key not in SECTIONS or SECTIONS[key].get('fixed') or SECTIONS[key].get('admin_only'):
        return False
    s = get_user_sidebar(user_id)
    if key in s['pinned']:
        s['pinned'].remove(key)
    if key not in s['hidden']:
        s['hidden'].append(key)
    save_user_sidebar(user_id, s['pinned'], s['hidden'])
    return True


def reset_sidebar(user_id):
    save_user_sidebar(user_id, [], [])
    return True


# ==================== СОБРАТЬ МЕНЮ ====================
def build_sidebar(user_id, is_admin=False):
    """
    Возвращает структуру меню для шаблона:
    {
      'main':       [{'key', 'name', 'icon', 'endpoint', 'pinned', ...}, ...],
      'hidden':     [...],   # не закреплённые (доступны в "Все разделы")
      'service':    [...],
      'admin':      [...],
    }
    Раздел, попавший в hidden_sections, не показывается вообще.
    """
    s = get_user_sidebar(user_id)
    pinned = [k for k in s['pinned'] if k in SECTIONS]
    hidden = [k for k in s['hidden'] if k in SECTIONS]

    def make_item(key, is_pinned=False):
        meta = SECTIONS[key]
        return {
            'key': key,
            'name': meta['name'],
            'icon': meta['icon'],
            'endpoint': meta['endpoint'],
            'pinned': is_pinned,
            'fixed': bool(meta.get('fixed')),
        }

    main = []
    hidden_list = []
    service = []
    admin = []

    for key, meta in SECTIONS.items():
        if meta.get('admin_only'):
            if is_admin:
                admin.append(make_item(key))
            continue

        group = meta.get('group')

        # Скрыто совсем — не показываем нигде
        if key in hidden:
            continue

        # Фиксированные
        if meta.get('fixed'):
            if group == 'service':
                service.append(make_item(key))
            else:
                main.append(make_item(key))
            continue

        # Опциональные: закреплённые → main, иначе → в "Все разделы"
        if key in pinned:
            main.append(make_item(key, is_pinned=True))
        else:
            hidden_list.append(make_item(key, is_pinned=False))

    return {
        'main': main,
        'hidden': hidden_list,
        'service': service,
        'admin': admin,
    }


def get_all_optional_sections():
    """Возвращает список опциональных разделов (для каталога в настройках)."""
    return [
        {'key': k, 'name': v['name'], 'icon': v['icon']}
        for k, v in SECTIONS.items()
        if not v.get('fixed') and not v.get('admin_only')
    ]

def get_hidden_sections(user_id):
    """Возвращает список скрытых разделов (для настроек)."""
    s = get_user_sidebar(user_id)
    return [
        {'key': k, 'name': SECTIONS[k]['name'], 'icon': SECTIONS[k]['icon']}
        for k in s['hidden'] if k in SECTIONS
    ]


def unhide_section(user_id, key):
    """Возвращает скрытый раздел обратно."""
    s = get_user_sidebar(user_id)
    if key in s['hidden']:
        s['hidden'].remove(key)
    save_user_sidebar(user_id, s['pinned'], s['hidden'])
    return True