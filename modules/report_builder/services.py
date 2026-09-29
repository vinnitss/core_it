"""
CRUD для сохранённых отчётов конструктора.
"""
import json
import pandas as pd
from sqlalchemy import text

from modules.core.utils import engine


def create_report(name, description, report_type, config,
                  owner_id=None, is_public=False, is_system=False):
    """Создать новый отчёт. Возвращает id."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO saved_reports 
                (name, description, report_type, config, owner_id, is_public, is_system)
            VALUES 
                (:name, :desc, :rtype, CAST(:config AS jsonb),
                 :owner, :public, :system)
            RETURNING id
        """), {
            'name': name,
            'desc': description,
            'rtype': report_type,
            'config': json.dumps(config, ensure_ascii=False),
            'owner': owner_id,
            'public': is_public,
            'system': is_system,
        })
        new_id = result.fetchone()[0]
        conn.commit()
    return int(new_id)

def update_report(report_id, name=None, description=None, config=None,
                  is_public=None):
    """Частичное обновление отчёта."""
    sets = []
    params = {'id': report_id}

    if name is not None:
        sets.append("name = :name")
        params['name'] = name
    if description is not None:
        sets.append("description = :desc")
        params['desc'] = description
    if config is not None:
        sets.append("config = CAST(:config AS jsonb)")
        params['config'] = json.dumps(config, ensure_ascii=False)
    if is_public is not None:
        sets.append("is_public = :public")
        params['public'] = is_public

    if not sets:
        return

    sets.append("updated_at = NOW()")

    with engine.connect() as conn:
        conn.execute(text(
            f"UPDATE saved_reports SET {', '.join(sets)} WHERE id = :id"
        ), params)
        conn.commit()

def delete_report(report_id):
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM saved_reports WHERE id = :id AND is_system = FALSE"),
            {'id': report_id}
        )
        conn.commit()


def get_report(report_id):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, name, description, report_type, config,
                   owner_id, is_public, is_system, created_at, updated_at
            FROM saved_reports WHERE id = :id
        """), {'id': report_id}).fetchone()
    if not row:
        return None

    cfg = row.config
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}

    return {
        'id': int(row.id),
        'name': row.name,
        'description': row.description,
        'report_type': row.report_type,
        'config': cfg,
        'owner_id': row.owner_id,
        'is_public': bool(row.is_public),
        'is_system': bool(row.is_system),
        'created_at': row.created_at,
        'updated_at': row.updated_at,
    }

def list_reports(user_id=None, include_public=True, include_system=True,
                 only_mine=False):
    """
    Возвращает список доступных пользователю отчётов.
    user_id=None — все отчёты (для админа).
    """
    where = []
    params = {}

    if user_id is not None and only_mine:
        where.append("owner_id = :uid")
        params['uid'] = user_id
    elif user_id is not None:
        conditions = []
        conditions.append("owner_id = :uid")
        params['uid'] = user_id
        if include_public:
            conditions.append("is_public = TRUE")
        if include_system:
            conditions.append("is_system = TRUE")
        where.append("(" + " OR ".join(conditions) + ")")

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, name, description, report_type, owner_id,
                   is_public, is_system, created_at, updated_at
            FROM saved_reports
            {where_sql}
            ORDER BY is_system DESC, updated_at DESC
        """), params).fetchall()

    return [{
        'id': int(r.id),
        'name': r.name,
        'description': r.description,
        'report_type': r.report_type,
        'owner_id': r.owner_id,
        'is_public': bool(r.is_public),
        'is_system': bool(r.is_system),
        'created_at': r.created_at,
        'updated_at': r.updated_at,
    } for r in rows]