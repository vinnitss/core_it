"""
Матчинг заявок к объектам справочника по текстам.
Версия 2: улучшенная токенизация и веса.
"""
import math
import re
from collections import defaultdict

import pandas as pd
from sqlalchemy import text

from modules.core.utils import engine, read_sql


STOP_WORDS = {
    'г', 'город', 'гор', 'и', 'на', 'при', 'в', 'с', 'о', 'от', 'до', 'по',
    'за', 'для', 'к', 'км', 'м', 'ул', 'улица', 'д', 'дом', 'стр', 'объект',
    'объекта', 'объекты', 'номер', 'телефон', 'интернет', 'связь', 'склад',
    # мусор из нумерации документов
    '№', 'бз', 'исд', 'дог', 'договор', 'счет', 'счёт', 'спец', 'спецификация',
    'заказ', 'заказа', 'соглашение', 'приложение', 'оферта',
}


# Максимальное количество объектов, в которых может встречаться токен.
# Если больше — токен бесполезен для различения.
MAX_OBJECTS_PER_TOKEN = 25


def tokenize(name, split_hyphen=False):
    """
    Разбивает строку на значимые токены (lowercase, ё→е, без пунктуации).

    split_hyphen=False по умолчанию: сохраняем 'усть-кут' как один токен,
    а не разбиваем на 'усть' и 'кут'.
    """
    if not name:
        return set()
    s = str(name).lower().replace('ё', 'е')
    s = re.sub(r'[.,;:()\[\]"\'«»]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    tokens = set()
    for raw in s.split():
        t = raw.strip('-.')
        if not t:
            continue
        # Отбрасываем токены с №
        if '№' in t:
            continue
        # Отбрасываем чистые числа
        if re.match(r'^\d+$', t):
            continue
        # Отбрасываем короткие
        if len(t) < 3:
            continue
        if t in STOP_WORDS:
            continue

        tokens.add(t)

        # Опционально: разбиваем дефис-составные
        if split_hyphen and ('-' in t or '/' in t):
            for part in re.split(r'[-/]', t):
                part = part.strip()
                if len(part) >= 4 and part not in STOP_WORDS and not re.match(r'^\d+$', part):
                    tokens.add(part)
    return tokens


def build_object_tokens():
    """
    Заполняет object_tokens: для каждого объекта — токены и веса.
    Вес = (1 / N) * log(len(token) + 1), где N — в скольких объектах встречается токен.
    Токены с N > MAX_OBJECTS_PER_TOKEN игнорируются.
    """
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM object_tokens;"))
        conn.commit()

    objects = read_sql("SELECT id, name FROM objects", engine)
    if objects.empty:
        return 0, 0, 0

    obj_tokens = {}
    token_objects = defaultdict(set)

    for _, o in objects.iterrows():
        oid = int(o['id'])
        tokens = tokenize(o['name'])
        obj_tokens[oid] = tokens
        for t in tokens:
            token_objects[t].add(oid)

    rows = []
    skipped_tokens = 0
    for oid, tokens in obj_tokens.items():
        for t in tokens:
            n = len(token_objects[t])
            if n > MAX_OBJECTS_PER_TOKEN:
                skipped_tokens += 1
                continue
            weight = (1.0 / n) * math.log(len(t) + 1)
            rows.append({
                'object_id': oid,
                'token': t,
                'weight': round(weight, 4),
            })

    if rows:
        df = pd.DataFrame(rows)
        # Уникальные пары (object_id, token) — на случай дублирования
        df = df.drop_duplicates(subset=['object_id', 'token'])
        df.to_sql('object_tokens', engine, if_exists='append', index=False, method='multi')

    return len(rows), len(token_objects), skipped_tokens


def match_application_text(app_text, token_index):
    """Возвращает список кандидатов, отсортированный по score desc."""
    if not app_text:
        return []
    tokens = tokenize(app_text)
    if not tokens:
        return []

    scores = {}
    for t in tokens:
        for oid, weight in token_index.get(t, []):
            entry = scores.setdefault(oid, {'score': 0.0, 'matched': [], 'count': 0})
            entry['score'] += weight
            entry['matched'].append(t)
            entry['count'] += 1

    result = [{
        'object_id': oid,
        'score': round(v['score'], 4),
        'count': v['count'],
        'matched_tokens': sorted(v['matched']),
    } for oid, v in scores.items()]
    result.sort(key=lambda x: (-x['score'], -x['count']))
    return result

def classify_confidence(candidates):
    """
    Определяет уровень уверенности.
    Новая логика: HIGH при score >= 1.5 (даже 1 токен),
    MEDIUM при score >= 0.8.
    """
    if not candidates:
        return 'NO_MATCH', []

    top = candidates[0]
    same_top = [c for c in candidates if abs(c['score'] - top['score']) < 0.01]

    # AMBIGUOUS — несколько равных кандидатов на верхнем месте
    if len(same_top) > 1:
        # Но если top явно выше остальных — не AMBIGUOUS
        if len(candidates) > len(same_top):
            second = candidates[len(same_top)]
            if second['score'] > 0 and top['score'] / second['score'] > 2.0:
                if top['score'] >= 1.5:
                    return 'HIGH', [top['object_id']]
                elif top['score'] >= 0.8:
                    return 'MEDIUM', [top['object_id']]
        return 'AMBIGUOUS', [c['object_id'] for c in same_top[:5]]

    # Одиночный кандидат
    if top['score'] >= 1.5:
        conf = 'HIGH'
    elif top['score'] >= 0.8:
        conf = 'MEDIUM'
    else:
        conf = 'LOW'

    return conf, [top['object_id']]

def run_matching_report(limit=None, with_projects=None):
    """
    Разведочный прогон. Ничего не пишет в БД.
    """
    tk = read_sql("""
        SELECT ot.token, ot.object_id, ot.weight, o.name
        FROM object_tokens ot
        JOIN objects o ON o.id = ot.object_id
    """, engine)

    if tk.empty:
        return {'error': 'object_tokens пуст. Запустите build_object_tokens().'}

    token_index = defaultdict(list)
    obj_names = {}
    for _, r in tk.iterrows():
        token_index[r['token']].append((int(r['object_id']), float(r['weight'])))
        obj_names[int(r['object_id'])] = r['name']

    where = ["(состояние_заявки IS NULL OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))"]
    params = {}
    if with_projects:
        where.append("проект = ANY(%(projects)s)")
        params['projects'] = with_projects

    where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT 
            номер_заявки, дата, назначение_платежа, договор_контрагента,
            проект, стг_подсказка_исд
        FROM applications
        {where_sql}
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    apps = read_sql(sql, engine, params=params)

    stats = defaultdict(int)
    examples = defaultdict(list)
    per_object = defaultdict(int)
    unassigned_examples = []

    for _, r in apps.iterrows():
        combined_text = f"{r['назначение_платежа'] or ''} {r['договор_контрагента'] or ''}"
        cands = match_application_text(combined_text, token_index)
        conf, chosen = classify_confidence(cands)
        stats[conf] += 1

        for oid in chosen:
            per_object[oid] += 1

        if len(examples[conf]) < 15:
            top3 = [{
                'object_id': c['object_id'],
                'name': obj_names.get(c['object_id'], '?'),
                'score': c['score'],
                'count': c['count'],
                'tokens': c['matched_tokens'],
            } for c in cands[:3]]
            examples[conf].append({
                'номер_заявки': r['номер_заявки'],
                'дата': str(r['дата']),
                'проект': r['проект'],
                'исд': r['стг_подсказка_исд'],
                'text': text[:200],
                'candidates': top3,
                'chosen_ids': chosen,
            })

    top_objects = sorted(per_object.items(), key=lambda x: -x[1])[:20]

    return {
        'total': len(apps),
        'stats': dict(stats),
        'examples': dict(examples),
        'top_objects': [{'name': obj_names.get(oid, '?'), 'count': cnt} for oid, cnt in top_objects],
    }

def save_matches(limit=None, auto_confirm_high=True, auto_confirm_medium=True):
    """
    Прогоняет матчинг по всем заявкам и сохраняет результат в БД.
      - applications.object_id
      - applications.object_match_confidence
      - applications.object_match_candidates (JSONB)
    
    HIGH/MEDIUM — записываются автоматически (если флаги True).
    AMBIGUOUS — записываются только кандидаты, object_id остаётся NULL.
    LOW/NO_MATCH — только кандидаты (для справки), object_id NULL.
    
    Перед запуском стирает прошлые матчи.
    Возвращает статистику.
    """
    import json

    tk = read_sql("""
        SELECT ot.token, ot.object_id, ot.weight, o.name
        FROM object_tokens ot
        JOIN objects o ON o.id = ot.object_id
    """, engine)

    if tk.empty:
        return {'error': 'object_tokens пуст. Запустите build_object_tokens().'}

    token_index = defaultdict(list)
    obj_names = {}
    for _, r in tk.iterrows():
        token_index[r['token']].append((int(r['object_id']), float(r['weight'])))
        obj_names[int(r['object_id'])] = r['name']

    where = ["(состояние_заявки IS NULL OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))"]
    where_sql = "WHERE " + " AND ".join(where)

    sql = f"""
        SELECT 
            номер_заявки, дата, назначение_платежа, договор_контрагента,
            проект, стг_подсказка_исд
        FROM applications
        {where_sql}
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    apps = read_sql(sql, engine, params={})

    stats = defaultdict(int)
    updates = []

    for _, r in apps.iterrows():
        combined_text = f"{r['назначение_платежа'] or ''} {r['договор_контрагента'] or ''}"
        cands = match_application_text(combined_text, token_index)
        conf, chosen = classify_confidence(cands)

        stats[conf] += 1

        # object_id присваиваем только для HIGH/MEDIUM
        object_id = None
        if conf == 'HIGH' and auto_confirm_high and chosen:
            object_id = chosen[0]
        elif conf == 'MEDIUM' and auto_confirm_medium and chosen:
            object_id = chosen[0]

        candidates_json = json.dumps([
            {'object_id': c['object_id'], 'name': obj_names.get(c['object_id'], '?'),
             'score': c['score'], 'count': c['count'], 'tokens': c['matched_tokens']}
            for c in cands[:5]
        ], ensure_ascii=False) if cands else '[]'

        updates.append({
            'num': r['номер_заявки'],
            'date': r['дата'],
            'object_id': object_id,
            'conf': conf,
            'candidates': candidates_json,
        })

    # Bulk update через временную таблицу
    if updates:
        upd_df = pd.DataFrame(updates)
        upd_df.to_sql('app_match_temp', engine, if_exists='replace', index=False)

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE applications a
                SET object_id = t.object_id::int,
                    object_match_confidence = t.conf,
                    object_match_candidates = t.candidates::jsonb
                FROM app_match_temp t
                WHERE a.номер_заявки = t.num AND a.дата = t.date::date;
            """))
            conn.execute(text("DROP TABLE app_match_temp;"))
            conn.commit()

    return {
        'total': len(apps),
        'saved': len(updates),
        'stats': dict(stats),
    }


def clear_matches():
    """Очищает все сохранённые матчи."""
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE applications
            SET object_id = NULL,
                object_match_confidence = NULL,
                object_match_candidates = NULL
        """))
        conn.commit()


def get_match_review(confidence=None, project=None, search=None,
                     page=1, per_page=50, only_unconfirmed=False):
    """
    Список заявок с сохранёнными матчами для ручной проверки.
    """
    where = ["object_match_confidence IS NOT NULL"]
    params = {}

    if confidence:
        where.append("object_match_confidence = %(conf)s")
        params['conf'] = confidence
    if project:
        where.append("проект = %(project)s")
        params['project'] = project
    if search:
        where.append("(номер_заявки ILIKE %(s)s OR назначение_платежа ILIKE %(s)s)")
        params['s'] = f"%{search}%"
    if only_unconfirmed:
        where.append("object_id IS NULL")

    where_sql = "WHERE " + " AND ".join(where)

    total = read_sql(
        f"SELECT count(*) AS c FROM applications {where_sql}",
        engine, params=params
    ).iloc[0, 0]

    offset = (page - 1) * per_page
    params['limit'] = per_page
    params['offset'] = offset

    df = read_sql(f"""
        SELECT 
            a.номер_заявки, a.дата, a.сумма_заявки, a.контрагент, a.проект,
            a.назначение_платежа, a.договор_контрагента,
            a.object_id, a.object_match_confidence, a.object_match_candidates,
            o.name AS object_name
        FROM applications a
        LEFT JOIN objects o ON o.id = a.object_id
        {where_sql}
        ORDER BY 
            CASE a.object_match_confidence
                WHEN 'AMBIGUOUS' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'HIGH' THEN 3
                ELSE 4
            END,
            a.дата DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """, engine, params=params)

    return {
        'rows': df.to_dict('records'),
        'total': int(total),
        'page': page,
        'per_page': per_page,
        'pages': (int(total) + per_page - 1) // per_page if total else 0,
    }

def update_application_match(номер_заявки, дата, object_id=None, action='confirm'):
    """
    Ручное действие по матчу.
      action = 'confirm'  — подтвердить текущий object_id (или выбранный)
      action = 'reject'   — отклонить матч (object_id = NULL, conf = 'REJECTED')
      action = 'set'      — установить конкретный object_id
    """
    with engine.connect() as conn:
        if action == 'reject':
            conn.execute(text("""
                UPDATE applications
                SET object_id = NULL,
                    object_match_confidence = 'REJECTED'
                WHERE номер_заявки = :num AND дата = :dt
            """), {'num': номер_заявки, 'dt': дата})
        else:
            conn.execute(text("""
                UPDATE applications
                SET object_id = :oid,
                    object_match_confidence = 'CONFIRMED'
                WHERE номер_заявки = :num AND дата = :dt
            """), {'oid': object_id, 'num': номер_заявки, 'dt': дата})
        conn.commit()