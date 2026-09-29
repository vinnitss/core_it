"""
Парсер ячейки «1 этап согласования» / «2 этап согласования».
Извлекает организацию, ФИО, телефон, email.
"""
import re

import pandas as pd


ORG_MARKERS = [
    'гсп', 'филиал', 'спб', 'питер', 'москва', 'русгаз',
    'газпром', 'инвест', 'шельф',
]


def _strip_html(s):
    return re.sub(r'<[^>]+>', ' ', s)


def parse_approvers_cell(text):
    """
    Возвращает список словарей:
        [{'organization', 'name', 'phone', 'email'}, ...]
    """
    if text is None or pd.isna(text):
        return []

    s = str(text).strip()
    if not s:
        return []

    # Специальный случай
    if 'не требуется согласование' in s.lower():
        return []

    # Обрезаем всё после «3 этап», «4 этап» и т.д.
    s = re.split(r'\b[3-9]\s*этап', s, flags=re.IGNORECASE)[0]
    s = s.strip()

    # Разбиваем по <br> и по переносам строк
    lines = re.split(r'<br\s*/?>|\r?\n', s)
    lines = [_strip_html(line).strip() for line in lines]
    lines = [line for line in lines if line]

    if not lines:
        return []

    # Организация — первая строка, если содержит маркер
    organization = None
    if any(m in lines[0].lower() for m in ORG_MARKERS):
        organization = lines.pop(0)

    names = []
    phones = []
    emails = []

    for line in lines:
        # Email
        found_emails = re.findall(r'[\w\.\-]+@[\w\.\-]+', line)
        if found_emails:
            emails.extend(found_emails)
            # После удаления email остальное может быть именем
            line_clean = re.sub(r'[\w\.\-]+@[\w\.\-]+', '', line).strip()
            if line_clean and re.match(r'^[А-ЯЁ][а-яё]', line_clean):
                parts = re.split(r'\s*/\s*', line_clean)
                for p in parts:
                    p = p.strip()
                    if p and re.match(r'^[А-ЯЁ][а-яё]', p):
                        names.append(p)
            continue

        # Телефон
        if re.search(r'\d{3,}', line) and (
            'тел' in line.lower()
            or '(' in line
            or '+' in line
            or re.match(r'^[\d\s\(\)\-\+доб\.]+$', line, re.IGNORECASE)
        ):
            phones.append(line)
            continue

        # Имя (2-3 слова с заглавных букв, без цифр)
        if re.match(r'^[А-ЯЁ][а-яё]+(\s+[А-ЯЁ][а-яё]+){1,2}', line):
            parts = re.split(r'\s*/\s*', line)
            for p in parts:
                p = p.strip()
                if p and re.match(r'^[А-ЯЁ][а-яё]', p):
                    names.append(p)
            continue

    # Собираем результат
    if names:
        return [{
            'organization': organization or '',
            'name': name,
            'phone': phones[0] if phones else '',
            'email': emails[0] if emails else '',
        } for name in names]

    # Нет имени — сохраняем хотя бы контакты
    if organization or phones or emails:
        return [{
            'organization': organization or '',
            'name': '',
            'phone': phones[0] if phones else '',
            'email': emails[0] if emails else '',
        }]

    return []


def normalize_isd(value):
    """Приводит ИСД к 7-значному виду: '30341' → '0030341'."""
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if not s or not s.replace('.0', '').isdigit():
        return s or None
    s = s.replace('.0', '')
    return s.zfill(7)


def normalize_project(value):
    """Убирает лишние пробелы в названии проекта."""
    if value is None or pd.isna(value):
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()