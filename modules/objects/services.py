"""
Токенизация текстов заявок и договоров для извлечения объектов.
Версия 3: исключение контрагентов и ФИО через данные из БД.
"""
import json
import re
import csv
import io
import os

from collections import Counter
from sqlalchemy import text as _text
import pandas as pd
from modules.core.utils import engine, read_sql

# ==================== СТОП-СЛОВА ====================
STOP_WORDS = {
    # общие служебные
    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то',
    'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же', 'вы', 'за',
    'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще',
    'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли',
    'если', 'уже', 'или', 'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь',
    'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
    'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя',
    'их', 'чем', 'была', 'сам', 'чтоб', 'без', 'будто', 'чего', 'раз', 'тоже',
    'себе', 'под', 'будет', 'ж', 'тогда', 'кто', 'этот', 'того', 'потому',
    'этого', 'какой', 'совсем', 'ним', 'здесь', 'этом', 'один', 'почти',
    'мой', 'тем', 'чтобы', 'нее', 'сейчас', 'были', 'куда', 'зачем', 'сказать',
    'всех', 'никогда', 'сегодня', 'можно', 'при', 'наконец', 'два', 'об',
    'другой', 'хоть', 'после', 'над', 'больше', 'тот', 'через', 'эти', 'нас',
    'про', 'всего', 'них', 'какая', 'много', 'разве', 'три', 'эту', 'моя',
    'впрочем', 'хорошо', 'свою', 'этой', 'перед', 'иногда', 'лучше', 'чуть',
    'том', 'нельзя', 'такой', 'им', 'более', 'всегда', 'конечно', 'всю', 'между',

    # базовые термины
    'руб', 'руб.', 'р.', 'шт', 'шт.', 'г.', 'гг.', 'год', 'года', 'году',
    'услуг', 'услуги', 'услуга', 'услугу', 'услуге', 'работ', 'работы', 'работа',
    'договор', 'договора', 'договору', 'договором', 'договоре', 'договоры',
    'заявка', 'заявки', 'заявке', 'заявку', 'заявок', 'заявками',
    'счет', 'счета', 'счету', 'счетом', 'счетов', 'счет-оферта', 'счёта',
    '№', 'номер', 'номера',
    'оплата', 'оплату', 'оплаты', 'платеж', 'платежа', 'платежи', 'платежом',
    'стоимость', 'сумма', 'суммы', 'сумме',
    'выполнение', 'выполнения', 'оказание', 'оказания', 'оказанием',
    'всего', 'итого', 'общая', 'общий',
    'исполнение', 'исполнения',
    'компания', 'общество', 'ооо', 'оао', 'зао', 'пао', 'ао', 'ип',
    'основании', 'соответствии',

    # месяцы и периоды
    'январь', 'января', 'январе', 'январю',
    'февраль', 'февраля', 'феврале', 'февралю',
    'март', 'марта', 'марте', 'марту',
    'апрель', 'апреля', 'апреле', 'апрелю',
    'май', 'мая', 'мае', 'маю',
    'июнь', 'июня', 'июне', 'июню',
    'июль', 'июля', 'июле', 'июлю',
    'август', 'августа', 'августе', 'августу',
    'сентябрь', 'сентября', 'сентябре', 'сентябрю',
    'октябрь', 'октября', 'октябре', 'октябрю',
    'ноябрь', 'ноября', 'ноябре', 'ноябрю',
    'декабрь', 'декабря', 'декабре', 'декабрю',
    'квартал', 'квартала', 'квартале',
    'полугодие', 'полугодия', 'год', 'года',
    'месяц', 'месяца', 'месяцев', 'период', 'периода',
    'день', 'дня', 'дней', 'суток',

    # общие бизнес-термины (по результатам анализа)
    'заказ', 'заказа', 'заказу', 'заказом', 'заказы', 'заказов',
    'бланк', 'бланка', 'бланку', 'бланком', 'бланки', 'бланков',
    'бланкзаказа', 'бланкзаказов',
    'спецификация', 'спецификации', 'спецификацию', 'спецификацией', 'спецификаций',
    'приложение', 'приложения', 'приложению', 'приложением', 'приложений',
    'соглашение', 'соглашения', 'соглашению', 'соглашением',
    'дополнительное', 'дополнительного', 'дополнительной', 'дополнительные', 'дополнительный',
    'допол', 'дополнит',
    'частичная', 'частичной', 'частичное', 'частичный', 'частичного',
    'частичоплата', 'частич', 'частичн',
    'полная', 'полной', 'полное', 'полный',
    'первая', 'первой', 'первое', 'первый', 'перв',
    'вторая', 'второй', 'второе', 'втор',
    'третья', 'третьей', 'третье', 'третий',
    'четвертая', 'четвёртая',
    'новая', 'новой', 'новое', 'новый',
    'старая', 'старой', 'старое', 'старый',
    'копия', 'копии', 'оригинал', 'оригинала',
    'письмо', 'письма', 'письму', 'письмом',
    'запрос', 'запроса', 'запросу',
    'уведомление', 'уведомления',
    'согласование', 'согласования',
    'претензия', 'претензии', 'претензию',
    'изменение', 'изменения', 'изменению',
    'проект', 'проекта', 'проекту', 'проекты', 'проектам',
    'руководитель', 'руководителя', 'руководителю',
    'директор', 'директора',
    'департамент', 'департамента',
    'управление', 'управления',
    'отдел', 'отдела',
    'подразделение', 'подразделения',
    'госпошлина', 'госпошлины', 'госпошлину', 'пошлина', 'пошлины',
    'плата', 'платы', 'плату', 'платой',
    'накладные', 'накладных', 'накладная', 'накладной',
    'перечисление', 'перечисления', 'перечислением',
    'телеметрия', 'телеметрии', 'телеметрию',
    'возмещение', 'возмещения', 'возмещением',
    'приказ', 'приказа', 'приказу', 'приказом',
    'газификация', 'газификации',
    'замена', 'замены', 'замену',
    'логистика', 'логистики',
    'доступ', 'доступа', 'доступу',
    'страховка', 'страховки',
    'связи', 'связь', 'связи',
    'факторинг', 'факторинга',
    'задание', 'задания', 'заданию',
    'арбитражного', 'арбитражный', 'арбитраж',
    'временный', 'временного', 'временная',
    'лицензионный', 'лицензионного', 'лицензионная',
    'профессиональный', 'профессионального',
    'консультант', 'консультанта', 'консультанты',
    'возмещения', 'компенсация', 'компенсации',
    'лизинг', 'лизинга',
    'аренда', 'аренды', 'аренду',
    'услуг', 'услуге', 'услугам',
    'интернет', 'интернета',
    'телефон', 'телефония', 'телефонии',
    'абонентская', 'абонентской', 'абонентская плата',
    'абплата', 'абон',
    'подписка', 'подписки',
    'поддержка', 'поддержки',
    'сопровождение', 'сопровождения',
    'оборудование', 'оборудования',
    'поставка', 'поставки', 'поставку',
    'обучение', 'обучения',
    'проезд', 'проезда', 'командировка', 'командировки',
    'проживание', 'проживания',
    'перевозка', 'перевозки',
    'хранение', 'хранения',
    'ремонт', 'ремонта', 'ремонту',
    'техобслуживание', 'техобслуживания',
    'экспертиза', 'экспертизы',
    'аудит', 'аудита',
    'отчет', 'отчета', 'отчёт', 'отчёта',
    'акт', 'акта', 'акты', 'актов',
    'сверка', 'сверки',
    'баланс', 'баланса',
    'инвентаризация', 'инвентаризации',

    # прилагательные от названий банков/филиалов
    'столичный', 'столичного', 'столичная',
    'дальневосточный', 'дальневосточного', 'дальневосточная',
    'уральский', 'уральского', 'уральская',
    'центральный', 'центрального', 'центральная',
    'северо-западный', 'северо-западного',
    'поволжский', 'поволжского', 'поволжская',
    'сибирский', 'сибирского',
    'южный', 'южного', 'южная',
    'северный', 'северного', 'северная',
    'восточный', 'восточного',
    'западный', 'западного',
    'московский', 'московского', 'московская',
    'российский', 'российского',

    # технические типы
    'счёт', 'счета', 'счёте',
    'операция', 'операции', 'операциям',
    'документ', 'документа', 'документы', 'документов',
    'файл', 'файла', 'файлы',
    'портал', 'портала',
    'сервис', 'сервиса',
    'информация', 'информации',
    'данные', 'данных',
    'система', 'системы',
    'модуль', 'модуля',
    'функция', 'функции',

    # операторы/сервисы
    'мегафон', 'мтс', 'билайн', 'ростелеком', 'теле2',
    'iridium', 'iridium.', 'omnicomm', 'microsoft', 'ripe',
    'контурэкстерн', 'контурдиадок', 'технокад-экспресс', 'техэксперт',
    'гранд-смета', 'триколор', 'авантел', 'ситекс', 'смс-информ',
    'мбитс', 'мбит', 'гбит', 'кбит',
    'триколор',

    # общие слова, попавшие в топ
    'госпошлина', 'возмещение', 'перечисление', 'консультант',
    'газификация', 'замена', 'логистика', 'доступ', 'страховка',
    'связи', 'факторинг', 'задание', 'арбитражного',
    'временный', 'лицензионный', 'профессиональный',
    'интернет', 'абонентская', 'сублицензионный', 'абплата',
    'it-услуг', 'ит-услуг', 'it-оборудования', 'ит-оборудования',
    'наклуслуги', 'накл', 'услугам',
    'ремонт', 'работ', 'работы',
    'проекта', 'проект', 'проект',

    # короткие/распространённые слова
    'перечисление', 'оплата', 'плата',
}


# ==================== МАРКЕРЫ ОБЪЕКТОВ ====================
OBJECT_MARKERS = {
    'месторождение', 'месторождения', 'месторождению', 'месторождении',
    'месторождением', 'месторождений', 'месторождениям', 'месторождениями',
    'местрожд', 'местрожд.', 'м/р',
    'гкм', 'гкм.', 'лу', 'л/у',
    'укпг', 'гпп', 'взис', 'дкс', 'кс',
    'куст', 'куста', 'кустов', 'кустам', 'кустах', 'кусте',
    'скважина', 'скважины', 'скважин', 'скважине', 'скважинам',
    'площадка', 'площадки', 'площадке', 'площадок',
    'лицензия', 'лицензии', 'лицензионный',
    'участок', 'участка', 'участке', 'участков',
    'объект', 'объекта', 'объекте', 'объектов',
    'установка', 'установки', 'установке',
    'эстакада', 'эстакады',
    'трубопровод', 'трубопровода',
    'газопровод', 'газопровода',
    'нефтепровод', 'нефтепровода',
    'конденсатопровод',
    'терминал', 'терминала',
    'станция', 'станции', 'станций',
    'подстанция', 'подстанции',
    'компрессорная', 'компрессорной',
    'электростанция', 'электростанции',
    'дорога', 'дороги', 'дорог',
    'мост', 'моста',
    'офис', 'офиса', 'офисе', 'офисов',
    'гтс', 'днс', 'цпс', 'псп',
    'бу', 'бк', 'скв',
}


# ==================== ПАТТЕРНЫ МУСОРА ====================
TRASH_PATTERNS = [
    r'^в\d+[а-я]?$',
    r'^\d{1,8}$',
    r'^стнг[\-\.]',
    r'^фд[\-\d]',
    r'^к\d+[\-\d]',
    r'^мтс$', r'^мегафон$', r'^билайн$', r'^ростелеком$', r'^теле2$',
    r'^[a-z]{1,2}$',
    r'^[а-я]{1,3}$',
    r'^[\d\-\.\/]+$',
    r'^.{1,3}$',
]


def _is_trash(token: str) -> bool:
    """Проверяет, является ли токен мусором."""
    if token in STOP_WORDS:
        return True
    for pattern in TRASH_PATTERNS:
        if re.match(pattern, token):
            return True
    return False


def _normalize_token(t: str) -> str:
    t = t.strip().lower()
    t = re.sub(r'^[^\w\-]+', '', t)
    t = re.sub(r'[^\w\-]+$', '', t)
    return t


def _load_exclude_sets():
    """Загружает множества контрагентов и ФИО для исключения."""
    counterparties = set()
    names = set()

    # Контрагенты из contracts
    try:
        df = read_sql("""
            SELECT DISTINCT LOWER(TRIM(counterparty)) AS cp
            FROM contracts
            WHERE counterparty IS NOT NULL AND counterparty != ''
        """, engine)
        for cp in df['cp'].dropna():
            counterparties.add(cp)
            # разбиваем на слова (для случая "МТС ПАО (бывшее ОАО)")
            for w in re.split(r'[\s\(\)]+', str(cp)):
                w = w.strip().strip('.,')
                if len(w) >= 4:
                    counterparties.add(w.lower())
    except Exception:
        pass

    # Контрагенты из applications
    try:
        df = read_sql("""
            SELECT DISTINCT LOWER(TRIM(контрагент)) AS cp
            FROM applications
            WHERE контрагент IS NOT NULL AND контрагент != ''
        """, engine)
        for cp in df['cp'].dropna():
            counterparties.add(cp)
            for w in re.split(r'[\s\(\)]+', str(cp)):
                w = w.strip().strip('.,')
                if len(w) >= 4:
                    counterparties.add(w.lower())
    except Exception:
        pass

    # Ответственные — разбиваем ФИО на слова
    try:
        df = read_sql("""
            SELECT DISTINCT ответственный FROM applications
            WHERE ответственный IS NOT NULL AND ответственный != ''
            UNION
            SELECT DISTINCT ответственный FROM contracts
            WHERE ответственный IS NOT NULL AND ответственный != ''
        """, engine)
        for name in df['ответственный'].dropna():
            for w in str(name).split():
                w = w.strip('.,').lower()
                if len(w) >= 4:
                    names.add(w)
    except Exception:
        pass

    return counterparties, names


def extract_tokens(text, source_field, source_id, exclude_set=None, min_length=4):
    r"""
    Извлекает токены из текста (ужесточённая логика).

    Оставляем только:
      1. Коды объектов: 2000714-0338, 31/0109, БУ_Сахалин и подобные
      2. Слово ПЕРЕД маркером: "Тас-Юряхского месторождения" → тас-юряхского
      3. Слово ПОСЛЕ маркера: "месторождение Южно-Киринское" → южно-киринское
      4. Топонимы-компаунды (с дефисом, длиной ≥ 6)
      5. Топонимы на -ское/-ский/-ская/-ской/-ово/-ево/-ино
    """
    if not text or pd.isna(text):
        return []

    exclude_set = exclude_set or set()
    original = str(text)
    original_tokens = re.findall(r'\S+', original)
    original_words = [re.sub(r'[^\wа-яА-ЯёЁ\-]', '', t) for t in original_tokens]
    original_words = [w for w in original_words if w]

    result = []
    seen = set()

    for i, word in enumerate(original_words):
        norm = _normalize_token(word)
        if not norm or len(norm) < min_length:
            continue
        if _is_trash(norm):
            continue
        if norm in exclude_set:
            continue

        is_candidate = False

        # 1. Код объекта
        if re.match(r'^\d{6,7}[\-\/]\d{3,5}$', norm):
            is_candidate = True

        # 2. Объектный код с префиксом БУ_, БК_, СКВ_ и т.п.
        elif re.match(r'^(бу|бк|скв|уч|лиц|газ|нефт|мест|куст|скваж)[_\-]', norm):
            is_candidate = True

        # 3. Слово ПЕРЕД маркером объекта
        elif i + 1 < len(original_words):
            next_norm = _normalize_token(original_words[i + 1])
            if next_norm in OBJECT_MARKERS:
                if not re.search(r'\d', norm):
                    is_candidate = True

        # 4. Слово ПОСЛЕ маркера объекта
        if not is_candidate and i > 0:
            prev_norm = _normalize_token(original_words[i - 1])
            if prev_norm in OBJECT_MARKERS:
                if not re.search(r'\d', norm):
                    is_candidate = True

        # 5. Топоним-компаунд с дефисом
        if not is_candidate and '-' in norm and not re.search(r'\d', norm) and len(norm) >= 6:
            # исключаем названия компаний (содержат типичные суффиксы)
            if not re.search(r'(ком|серв|сист|логист|торг|строй|пром|инвест|техно|инфо|софт)', norm):
                is_candidate = True

        # 6. Топоним на -ское/-ский/-ская/-ской/-ово/-ево/-ино
        if not is_candidate and not re.search(r'\d', norm):
            if re.search(r'(ское|ский|ская|ской|ово|ево|ино|ская|ский)$', norm):
                if len(norm) >= 6:
                    is_candidate = True

        if is_candidate and norm not in seen:
            seen.add(norm)
            result.append({
                'token': norm,
                'source_field': source_field,
                'source_id': source_id,
                'example': original[:200],
            })

    return result


def rebuild_object_tokens():
    """
    Проходит по всем заявкам и договорам, извлекает токены, сохраняет в БД.
    """
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM object_tokens_raw;"))
        conn.commit()

    # Загружаем списки исключений (контрагенты, ФИО)
    counterparties, names = _load_exclude_sets()
    exclude_set = counterparties | names

    all_tokens = []

    apps = read_sql("""
        SELECT 
            номер_заявки || '|' || дата::text AS sid,
            назначение_платежа,
            договор_контрагента
        FROM applications
        WHERE (состояние_заявки IS NULL 
               OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
    """, engine)

    for _, r in apps.iterrows():
        sid = r['sid']
        all_tokens.extend(extract_tokens(r['назначение_платежа'], 'назначение_платежа', sid, exclude_set))
        all_tokens.extend(extract_tokens(r['договор_контрагента'], 'договор_контрагента', sid, exclude_set))

    contracts = read_sql("""
        SELECT external_code AS sid, matching_text
        FROM contracts
        WHERE matching_text IS NOT NULL AND matching_text != ''
    """, engine)

    for _, r in contracts.iterrows():
        all_tokens.extend(extract_tokens(r['matching_text'], 'договор', r['sid'], exclude_set))

    if not all_tokens:
        return 0

    counter = Counter()
    examples_map = {}

    for t in all_tokens:
        key = t['token']
        counter[key] += 1
        if key not in examples_map:
            examples_map[key] = []
        if len(examples_map[key]) < 5 and t['example'] not in examples_map[key]:
            examples_map[key].append(t['example'][:200])

    MIN_OCCURRENCES = 2
    rows = []
    for token, count in counter.most_common():
        if count < MIN_OCCURRENCES:
            continue
        rows.append({
            'token': token,
            'source_field': 'mixed',
            'source_id': '',
            'occurrences': count,
            'examples': json.dumps(examples_map.get(token, []), ensure_ascii=False),
        })

    if rows:
        df = pd.DataFrame(rows)
        df.to_sql('object_tokens_raw', engine, if_exists='append', index=False, method='multi')

    return len(rows)


def get_tokens(page=1, per_page=100, min_occurrences=5, search=None):
    """Возвращает пагинированный список токенов."""
    offset = (page - 1) * per_page

    where = ["occurrences >= %(min_occ)s"]
    params = {'min_occ': min_occurrences, 'limit': per_page, 'offset': offset}

    if search:
        where.append("token ILIKE %(search)s")
        params['search'] = f"%{search}%"

    where_sql = "WHERE " + " AND ".join(where)

    count = read_sql(
        f"SELECT count(*) FROM object_tokens_raw {where_sql}",
        engine, params=params
    ).iloc[0, 0]

    df = read_sql(f"""
        SELECT id, token, occurrences, examples
        FROM object_tokens_raw
        {where_sql}
        ORDER BY occurrences DESC, token ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """, engine, params=params)

    tokens = []
    for _, r in df.iterrows():
        try:
            examples = json.loads(r['examples']) if r['examples'] else []
        except Exception:
            examples = []
        tokens.append({
            'id': int(r['id']),
            'token': r['token'],
            'occurrences': int(r['occurrences']),
            'examples': examples,
        })

    return {
        'tokens': tokens,
        'total': int(count),
        'page': page,
        'per_page': per_page,
        'pages': (int(count) + per_page - 1) // per_page if count else 0,
    }
# ==================== ОБЪЕКТЫ ====================
def _read_csv_with_fallback(path):
    """Пробует UTF-8, потом cp1251."""
    for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'windows-1251'):
        try:
            with open(path, 'r', encoding=enc, newline='') as f:
                return list(csv.DictReader(f, delimiter=';'))
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось прочитать CSV ни в одной из кодировок")


def import_objects_from_csv(file_path):
    """
    Импорт объектов из CSV. Ожидает столбцы:
      id, name, info, lat, lon, type, status
    Дополнительно (если есть): code, project, field, short_name, ответственный
    Обновляет по code (или по id, если code нет).
    Возвращает (added, updated, total).
    """
    rows = _read_csv_with_fallback(file_path)
    if not rows:
        return 0, 0, 0

    added = updated = 0

    with engine.connect() as conn:
        for r in rows:
            name = (r.get('name') or '').strip()
            if not name:
                continue

            code = (r.get('code') or '').strip() or None
            project = (r.get('project') or '').strip() or None
            field = (r.get('field') or '').strip() or None
            short_name = (r.get('short_name') or '').strip() or None
            ответственный = (r.get('ответственный') or '').strip() or None
            info = (r.get('info') or '').strip() or None
            otype = (r.get('type') or '').strip() or None
            status = (r.get('status') or '').strip() or None

            def _num(v):
                if not v or str(v).strip() == '':
                    return None
                try:
                    return float(str(v).replace(',', '.'))
                except ValueError:
                    return None

            lat = _num(r.get('lat'))
            lon = _num(r.get('lon'))

            # Проверяем существование по code
            existing_id = None
            if code:
                row = conn.execute(
                    _text("SELECT id FROM objects WHERE code = :c"),
                    {'c': code}
                ).fetchone()
                if row:
                    existing_id = int(row[0])

            if existing_id:
                conn.execute(_text("""
                    UPDATE objects SET
                        name = :name,
                        short_name = :short_name,
                        type = :type,
                        status = :status,
                        project = :project,
                        field = :field,
                        lat = :lat,
                        lon = :lon,
                        ответственный = :resp,
                        info = :info
                    WHERE id = :id
                """), {
                    'id': existing_id, 'name': name, 'short_name': short_name,
                    'type': otype, 'status': status, 'project': project,
                    'field': field, 'lat': lat, 'lon': lon,
                    'resp': ответственный, 'info': info,
                })
                updated += 1
            else:
                conn.execute(_text("""
                    INSERT INTO objects
                        (code, name, short_name, type, status, project, field,
                         lat, lon, ответственный, info)
                    VALUES
                        (:code, :name, :short_name, :type, :status, :project, :field,
                         :lat, :lon, :resp, :info)
                """), {
                    'code': code, 'name': name, 'short_name': short_name,
                    'type': otype, 'status': status, 'project': project,
                    'field': field, 'lat': lat, 'lon': lon,
                    'resp': ответственный, 'info': info,
                })
                added += 1

        conn.commit()

    return added, updated, len(rows)


def generate_missing_codes():
    """
    Присваивает коды (001, 002, ...) объектам без кода.
    Учитывает максимальный существующий.
    """
    with engine.connect() as conn:
        # Максимальный существующий код
        row = conn.execute(_text("""
            SELECT COALESCE(MAX(CAST(code AS INTEGER)), 0) 
            FROM objects 
            WHERE code ~ '^[0-9]+$'
        """)).fetchone()
        next_num = int(row[0]) + 1

        # Объекты без кода
        rows = conn.execute(_text("""
            SELECT id FROM objects 
            WHERE code IS NULL OR code = '' 
            ORDER BY id
        """)).fetchall()

        for r in rows:
            code = f"{next_num:03d}"
            conn.execute(_text(
                "UPDATE objects SET code = :c WHERE id = :id"
            ), {'c': code, 'id': int(r[0])})
            next_num += 1

        conn.commit()
    return len(rows)


def get_objects(project=None, otype=None, status=None, search=None):
    """Список объектов с фильтрами."""
    where = []
    params = {}
    if project:
        where.append("project = %(project)s")
        params['project'] = project
    if otype:
        where.append("type = %(type)s")
        params['type'] = otype
    if status:
        where.append("status = %(status)s")
        params['status'] = status
    if search:
        where.append("(name ILIKE %(search)s OR code ILIKE %(search)s OR project ILIKE %(search)s)")
        params['search'] = f"%{search}%"

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    df = read_sql(f"""
        SELECT id, code, name, short_name, type, status, project, field,
               lat, lon, ответственный, info
        FROM objects
        {where_sql}
        ORDER BY project NULLS LAST, name
    """, engine, params=params)
    return df.to_dict('records')


def get_object_filter_options():
    """Уникальные проекты/типы/статусы для фильтров."""
    projects = read_sql("""
        SELECT DISTINCT project FROM objects
        WHERE project IS NOT NULL AND project != ''
        ORDER BY project
    """, engine)['project'].tolist()

    types = read_sql("""
        SELECT DISTINCT type FROM objects
        WHERE type IS NOT NULL AND type != ''
        ORDER BY type
    """, engine)['type'].tolist()

    statuses = read_sql("""
        SELECT DISTINCT status FROM objects
        WHERE status IS NOT NULL AND status != ''
        ORDER BY status
    """, engine)['status'].tolist()

    return {'projects': projects, 'types': types, 'statuses': statuses}


def get_object_by_id(obj_id):
    row = read_sql("""
        SELECT id, code, name, short_name, type, status, project, field,
               lat, lon, ответственный, info, created_at
        FROM objects WHERE id = %(id)s
    """, engine, params={'id': obj_id})
    return row.to_dict('records')[0] if not row.empty else None


def get_objects_for_map(project=None, otype=None, status=None):
    """Объекты с координатами для карты."""
    where = ["lat IS NOT NULL", "lon IS NOT NULL"]
    params = {}
    if project:
        where.append("project = %(project)s")
        params['project'] = project
    if otype:
        where.append("type = %(type)s")
        params['type'] = otype
    if status:
        where.append("status = %(status)s")
        params['status'] = status

    where_sql = "WHERE " + " AND ".join(where)

    df = read_sql(f"""
        SELECT id, code, name, type, status, project, field, lat, lon, info
        FROM objects
        {where_sql}
        ORDER BY project NULLS LAST, name
    """, engine, params=params)

    return [{
        'id': int(r['id']),
        'code': r['code'] or '',
        'name': r['name'],
        'type': r['type'] or '',
        'status': r['status'] or '',
        'project': r['project'] or '',
        'field': r['field'] or '',
        'lat': float(r['lat']),
        'lon': float(r['lon']),
        'info': r['info'] or '',
    } for _, r in df.iterrows()]


def delete_object(obj_id):
    with engine.connect() as conn:
        conn.execute(_text("DELETE FROM objects WHERE id = :id"), {'id': obj_id})
        conn.commit()