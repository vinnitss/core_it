"""
Сервис справочника согласующих по проектам.
"""
import logging

import pandas as pd
from sqlalchemy import text

from modules.core.utils import engine, read_sql
from modules.approvers.parser import (
    parse_approvers_cell, normalize_isd, normalize_project,
)

logger = logging.getLogger(__name__)


# ==================== ЗАГРУЗКА ДАННЫХ ====================
def _get_or_create_approver(conn, name, email, phone, organization):
    """Возвращает id согласующего, создаёт при отсутствии."""
    if not name:
        return None
    # Ищем по (name, COALESCE(email,''))
    row = conn.execute(text("""
        SELECT id FROM approvers
        WHERE name = :n AND COALESCE(email, '') = COALESCE(:e, '')
        LIMIT 1
    """), {'n': name, 'e': email or ''}).fetchone()
    if row:
        return int(row[0])

    result = conn.execute(text("""
        INSERT INTO approvers (name, email, phone, organization)
        VALUES (:n, :e, :p, :o)
        RETURNING id
    """), {'n': name, 'e': email or None, 'p': phone or None, 'o': organization or None})
    new_id = int(result.fetchone()[0])
    return new_id


def _get_or_create_project(conn, isd, project, platform, registry_type):
    """Возвращает id проекта согласования."""
    row = conn.execute(text("""
        SELECT id FROM approval_projects
        WHERE COALESCE(isd, '') = COALESCE(:i, '') AND project = :p
        LIMIT 1
    """), {'i': isd, 'p': project}).fetchone()
    if row:
        return int(row[0])

    result = conn.execute(text("""
        INSERT INTO approval_projects (isd, project, platform, registry_type)
        VALUES (:i, :p, :pl, :rt)
        RETURNING id
    """), {
        'i': isd, 'p': project,
        'pl': platform or None, 'rt': registry_type or None,
    })
    return int(result.fetchone()[0])


def _link_approver(conn, project_id, stage, approver_id, order_num):
    """Создаёт связь согласующий ↔ проект ↔ этап."""
    if approver_id is None:
        return
    conn.execute(text("""
        INSERT INTO project_stage_approvers 
            (project_id, stage, approver_id, order_num)
        VALUES (:pid, :s, :aid, :o)
        ON CONFLICT (project_id, stage, approver_id) DO NOTHING
    """), {'pid': project_id, 's': stage, 'aid': approver_id, 'o': order_num})


# ==================== ИМПОРТ ИЗ EXCEL ====================
def import_approvers_from_excel(file_path, replace=True):
    """
    Импортирует справочник согласующих из Excel.
    С подробным логированием каждой строки.
    """
    df = pd.read_excel(file_path, dtype=str)
    df.columns = df.columns.str.strip()

    def find_col(*variants):
        for col in df.columns:
            col_low = col.lower()
            for v in variants:
                if v.lower() in col_low:
                    return col
        return None

    col_isd = find_col('исд')
    col_project = find_col('проект')
    col_platform = find_col('площадка')
    col_registry = find_col('реестровость')
    col_stage1 = find_col('1 этап')
    col_stage2 = find_col('2 этап')

    if not col_project or not col_stage1 or not col_stage2:
        raise ValueError("Не найдены обязательные столбцы")

    print(f"=== ИМПОРТ СОГЛАСУЮЩИХ ===", flush=True)
    print(f"Строк в файле: {len(df)}", flush=True)

    projects_count = 0
    approvers_created = 0
    links_count = 0
    errors = []

    with engine.connect() as conn:
        if replace:
            print("Очищаем таблицы...", flush=True)
            conn.execute(text("DELETE FROM project_stage_approvers;"))
            conn.execute(text("DELETE FROM approvers;"))
            conn.execute(text("DELETE FROM approval_projects;"))
            conn.commit()
            print("Таблицы очищены", flush=True)

        for idx, row in df.iterrows():
            try:
                project_name = normalize_project(row.get(col_project))
                if not project_name:
                    print(f"Row {idx}: пропуск (нет проекта)", flush=True)
                    continue

                isd = normalize_isd(row.get(col_isd)) if col_isd else None
                platform = (str(row.get(col_platform) or '')).strip() or None
                registry_type = (str(row.get(col_registry) or '')).strip().lower() or None

                # Проект
                project_id = _get_or_create_project(
                    conn, isd, project_name, platform, registry_type
                )
                projects_count += 1
                print(f"Row {idx}: project_id={project_id}, isd={isd}, project={project_name}", flush=True)

                # Этап 1
                stage1_data = parse_approvers_cell(row.get(col_stage1))
                print(f"  stage1: {len(stage1_data)} человек", flush=True)
                for i, a in enumerate(stage1_data):
                    aid = _get_or_create_approver(
                        conn, a['name'], a['email'], a['phone'], a['organization']
                    )
                    if aid:
                        _link_approver(conn, project_id, 1, aid, i)
                        links_count += 1
                        if i == 0:
                            approvers_created += 1

                # Этап 2
                stage2_data = parse_approvers_cell(row.get(col_stage2))
                print(f"  stage2: {len(stage2_data)} человек", flush=True)
                for i, a in enumerate(stage2_data):
                    aid = _get_or_create_approver(
                        conn, a['name'], a['email'], a['phone'], a['organization']
                    )
                    if aid:
                        _link_approver(conn, project_id, 2, aid, i)
                        links_count += 1
                        if i == 0:
                            approvers_created += 1

            except Exception as e:
                import traceback
                err = f"Row {idx}: {e}"
                errors.append(err)
                print(f"❌ {err}", flush=True)
                print(traceback.format_exc(), flush=True)

        print("Коммитим изменения...", flush=True)
        conn.commit()
        print("Готово", flush=True)

    unique_approvers = read_sql(
        "SELECT COUNT(*) AS c FROM approvers", engine
    ).iloc[0]['c']

    print(f"\n=== РЕЗУЛЬТАТ ===", flush=True)
    print(f"Проектов создано: {projects_count}", flush=True)
    print(f"Уникальных согласующих: {unique_approvers}", flush=True)
    print(f"Связей: {links_count}", flush=True)
    if errors:
        print(f"Ошибок: {len(errors)}", flush=True)
        for e in errors[:10]:
            print(f"  {e}", flush=True)

    return {
        'projects': projects_count,
        'approvers': int(unique_approvers),
        'links': links_count,
        'errors': errors,
    }


# ==================== ЧТЕНИЕ ====================
def list_projects(search=None, isd=None, platform=None, registry_type=None,
                  approver_id=None):
    """
    Возвращает список проектов согласования со всеми согласующими.
    """
    where = []
    params = {}

    if search:
        where.append("(p.project ILIKE %(search)s OR p.isd ILIKE %(search)s)")
        params['search'] = f'%{search}%'
    if isd:
        where.append("p.isd = %(isd)s")
        params['isd'] = isd
    if platform:
        where.append("p.platform = %(platform)s")
        params['platform'] = platform
    if registry_type:
        where.append("p.registry_type = %(rt)s")
        params['rt'] = registry_type

    if approver_id:
        where.append("""
            EXISTS (
                SELECT 1 FROM project_stage_approvers psa
                WHERE psa.project_id = p.id AND psa.approver_id = %(aid)s
            )
        """)
        params['aid'] = int(approver_id)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    projects = read_sql(f"""
        SELECT 
            p.id, p.isd, p.project, p.platform, p.registry_type,
            p.created_at, p.updated_at
        FROM approval_projects p
        {where_sql}
        ORDER BY p.project, p.isd
    """, engine, params=params).to_dict('records')

    if not projects:
        return []

    ids = [p['id'] for p in projects]

    links = read_sql("""
        SELECT 
            psa.project_id, psa.stage, psa.order_num,
            a.id AS approver_id, a.name, a.email, a.phone, a.organization
        FROM project_stage_approvers psa
        JOIN approvers a ON a.id = psa.approver_id
        WHERE psa.project_id = ANY(%(ids)s)
        ORDER BY psa.stage, psa.order_num, a.name
    """, engine, params={'ids': ids}).to_dict('records')

    # Группируем
    from collections import defaultdict
    by_project = defaultdict(lambda: {'stage1': [], 'stage2': []})
    for link in links:
        stage = link['stage']
        bucket = 'stage1' if stage == 1 else 'stage2'
        by_project[link['project_id']][bucket].append({
            'id': link['approver_id'],
            'name': link['name'],
            'email': link['email'] or '',
            'phone': link['phone'] or '',
            'organization': link['organization'] or '',
        })

    for p in projects:
        p['stage1'] = by_project[p['id']]['stage1']
        p['stage2'] = by_project[p['id']]['stage2']

    return projects


def get_project(project_id):
    """Один проект согласования с согласующими."""
    data = list_projects()
    for p in data:
        if p['id'] == project_id:
            return p
    return None


def list_all_approvers():
    """Список всех согласующих (для фильтра)."""
    return read_sql("""
        SELECT id, name, email, phone, organization
        FROM approvers
        ORDER BY name
    """, engine).to_dict('records')


def get_filter_options():
    """Уникальные значения для фильтров."""
    platforms = read_sql("""
        SELECT DISTINCT platform FROM approval_projects
        WHERE platform IS NOT NULL AND platform != ''
        ORDER BY platform
    """, engine)['platform'].tolist()

    registry_types = read_sql("""
        SELECT DISTINCT registry_type FROM approval_projects
        WHERE registry_type IS NOT NULL AND registry_type != ''
        ORDER BY registry_type
    """, engine)['registry_type'].tolist()

    isds = read_sql("""
        SELECT DISTINCT isd FROM approval_projects
        WHERE isd IS NOT NULL AND isd != ''
        ORDER BY isd
    """, engine)['isd'].tolist()

    return {
        'platforms': platforms,
        'registry_types': registry_types,
        'isds': isds,
    }


# ==================== CRUD ПРОЕКТОВ ====================
def create_project(isd, project, platform, registry_type):
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO approval_projects (isd, project, platform, registry_type)
            VALUES (:i, :p, :pl, :rt)
            RETURNING id
        """), {
            'i': isd or None, 'p': project.strip(),
            'pl': platform or None, 'rt': registry_type or None,
        })
        pid = int(result.fetchone()[0])
        conn.commit()
    return pid


def update_project(project_id, isd, project, platform, registry_type):
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE approval_projects
            SET isd = :i, project = :p, platform = :pl, registry_type = :rt,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': project_id,
            'i': isd or None, 'p': project.strip(),
            'pl': platform or None, 'rt': registry_type or None,
        })
        conn.commit()


def delete_project(project_id):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM approval_projects WHERE id = :id"),
                     {'id': project_id})
        conn.commit()


# ==================== CRUD СОГЛАСУЮЩИХ НА ЭТАПЕ ====================
def add_approver_to_stage(project_id, stage, name, email='', phone='', organization=''):
    """
    Добавляет согласующего в проект на указанный этап.
    Если согласующий уже есть в справочнике — использует его.
    """
    with engine.connect() as conn:
        aid = _get_or_create_approver(conn, name, email, phone, organization)
        if not aid:
            return False
        _link_approver(conn, project_id, stage, aid, 0)
        conn.commit()
    return True


def remove_approver_from_stage(project_id, stage, approver_id):
    with engine.connect() as conn:
        conn.execute(text("""
            DELETE FROM project_stage_approvers
            WHERE project_id = :pid AND stage = :s AND approver_id = :aid
        """), {'pid': project_id, 's': stage, 'aid': approver_id})
        conn.commit()


# ==================== УТИЛИТЫ ДЛЯ ВИДЖЕТА ====================
def get_approvers_for_isd_project(isd, project):
    """
    Возвращает словарь:
        {'stage1': [...], 'stage2': [...]}
    по паре (ИСД, проект).
    """
    if not project:
        return {'stage1': [], 'stage2': []}

    rows = read_sql("""
        SELECT 
            psa.stage, psa.order_num,
            a.name, a.email, a.phone, a.organization
        FROM approval_projects p
        JOIN project_stage_approvers psa ON psa.project_id = p.id
        JOIN approvers a ON a.id = psa.approver_id
        WHERE COALESCE(p.isd, '') = COALESCE(%(isd)s, '')
          AND p.project = %(project)s
        ORDER BY psa.stage, psa.order_num, a.name
    """, engine, params={'isd': isd or '', 'project': project})

    result = {'stage1': [], 'stage2': []}
    for _, r in rows.iterrows():
        bucket = 'stage1' if r['stage'] == 1 else 'stage2'
        result[bucket].append({
            'name': r['name'],
            'email': r['email'] or '',
            'phone': r['phone'] or '',
            'organization': r['organization'] or '',
        })
    return result


def get_approvers_map_for_pairs(pairs):
    """
    Массовая функция для виджета.
    pairs: [(isd, project), ...]
    Возвращает dict: {(isd, project): {'stage1': [...], 'stage2': [...]}}
    """
    if not pairs:
        return {}

    # Достаём все проекты разом
    result = {}
    for isd, project in pairs:
        result[(isd, project)] = get_approvers_for_isd_project(isd, project)
    return result