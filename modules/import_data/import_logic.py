import re
import pandas as pd
from datetime import datetime
from modules.core.utils import engine, normalize_date, clean_money
from sqlalchemy import text

BEZREESTROVIY_ISD = {
    '0036045', '0025948', '0026977', '0034230',
    '0032259', '0031112', '0031124', '0026099'
}

MONTHS = {
    'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
    'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12
}

def clean_rp_number(value):
    """Очищает номер РП. Возвращает None для мусорных значений."""
    if pd.isna(value):
        return None
    s = str(value).strip()

    # Мусорные значения — возвращаем None
    garbage_patterns = [
        'номер не заполнен',
        'не заполнен',
        'нет',
        'нет данных',
        'nan',
        'none',
    ]
    s_lower = s.lower()
    for pattern in garbage_patterns:
        if pattern in s_lower:
            return None

    # Убираем префикс «РП »
    s = re.sub(r'^РП\s+', '', s).strip()

    return s if s else None

def clean_register_number(value):
    if pd.isna(value):
        return ''
    s = str(value).strip()
    if ' ' in s:
        s = s.split(' ')[0]
    return s.strip() if s else None

def extract_period(text):
    """
    Извлекает период услуги из текста назначения платежа.
    Сначала применяется старая логика ("за <месяц> <год> г."),
    если она не сработала — ищется дата счёта (после "от ...").
    Дата договора игнорируется.
    """
    if pd.isna(text) or str(text).strip() == '':
        return None

    s = str(text)

    # === 1. Старая логика: "за <месяц> <год> г." ===
    pattern_old = r'за\s+([а-яА-Я]+)\s+(\d{4})\s*г?\.?'
    match_old = re.search(pattern_old, s, re.IGNORECASE)
    if match_old:
        month_name = match_old.group(1).lower()
        year = int(match_old.group(2))
        if month_name in MONTHS:
            return datetime(year, MONTHS[month_name], 1).date()

    # === 2. Новая логика: дата счёта (после "от ДД.ММ.ГГ(ГГ)") ===
    for m in re.finditer(
        r'от\s+(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\s*г?\.?',
        s, re.IGNORECASE
    ):
        start = m.start()
        context_before = s[max(0, start - 60):start].lower()

        # Если рядом перед "от" упоминается договор — пропускаем эту дату
        pos_dogovor = context_before.rfind('договор')
        pos_schet = max(
            context_before.rfind('счет'),
            context_before.rfind('счёт'),
            context_before.rfind('счет-оферт'),
            context_before.rfind('счёт-оферт'),
        )

        # Пропускаем, если это дата договора
        if pos_dogovor != -1 and pos_dogovor > pos_schet:
            continue

        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).date()
        except ValueError:
            continue

    return None

#def extract_period(text):
#    if pd.isna(text) or text == '':
#        return None
#    pattern = r'за\s+([а-яА-Я]+)\s+(\d{4})\s*г?\.?'
#    match = re.search(pattern, str(text), re.IGNORECASE)
#    if match:
#        month_name = match.group(1).lower()
#        year = int(match.group(2))
#        if month_name in MONTHS:
#            return datetime(year, MONTHS[month_name], 1).date()
#    return None

def agg_text(series):
    unique = series.dropna().unique()
    return '; '.join(unique) if len(unique) > 0 else None

def agg_sum(series):
    return series.sum()

def agg_first(series):
    return series.dropna().iloc[0] if not series.dropna().empty else None

def agg_any(series):
    return series.any() if not series.empty else False

def find_column(df, patterns):
    # 1. Точное совпадение (без учёта регистра)
    for col in df.columns:
        col_lower = col.lower().strip()
        for pattern in patterns:
            if pattern.lower().strip() == col_lower:
                return col
    # 2. По подстроке (только если точного нет)
    for col in df.columns:
        col_lower = col.lower()
        for pattern in patterns:
            if pattern.lower() in col_lower:
                return col
    return None

def rename_columns_by_pattern(df, mapping):
    rename_dict = {}
    for pattern, new_name in mapping.items():
        col = find_column(df, [pattern])
        if col and col not in rename_dict.values():
            rename_dict[col] = new_name
    if rename_dict:
        df = df.rename(columns=rename_dict)
    return df

def load_and_clean_applications(file_path):
    df = pd.read_excel(file_path, sheet_name='Лист_1', dtype=str)
    df = df[df['Номер заявки'].notna()].copy()
    df.columns = df.columns.str.strip().str.replace(' ', '_')
    mapping_app = {
    'Платежное_поручение': 'Платежное_поручение_исходящее',
    'Номер_РП': 'Номер_РП',
    'Дата': 'Дата',
    'Сумма_заявки': 'Сумма_заявки',
    'Сумма_ПП': 'Сумма_ПП',
    'Назначение_платежа': 'Назначение_платежа',
    'Код_договора': 'Договор_код',                       # <-- код договора
    'Код_проекта': 'Код',                                # <-- код проекта
    'Договор_контрагента': 'Договор_контрагента',        # если столбец ещё есть в файле
    'Документ_расчетов_с_контрагентом': 'Документ_расчетов_с_контрагентом',
    'Документ_расчетов': 'Документ_расчетов_с_контрагентом',
    'Статус_согласования': 'Статус_согласования',
    'Дата_последнего_статуса': 'Дата_последнего_статуса',
    'Замечания_ДФ': 'Замечания_ДФ',
    'Состояние_заявки': 'Состояние_заявки',
    'Ответственный': 'Ответственный',
    'Дата_оплаты_фактич': 'Дата_оплаты_фактич',
    'Оплачена': 'Оплачена',
}
    df = rename_columns_by_pattern(df, mapping_app)
    for req in ['Номер_заявки', 'Дата', 'Сумма_заявки']:
        if req not in df.columns:
            raise KeyError(f"Столбец '{req}' не найден. Доступны: {list(df.columns)}")
    df['Номер_РП_чистый'] = df.get('Номер_РП', '').apply(clean_rp_number)
    df['Дата_без_времени'] = df['Дата'].apply(normalize_date)
    df['Сумма_заявки'] = df['Сумма_заявки'].astype(str).str.replace(',', '.').astype(float)
    # Обработка даты фактической оплаты
    if 'Дата_оплаты_фактич' in df.columns:
        df['Дата_оплаты_фактич'] = df['Дата_оплаты_фактич'].apply(normalize_date)
    else:
        df['Дата_оплаты_фактич'] = None
    if 'Сумма_ПП' in df.columns:
        df['Сумма_ПП'] = df['Сумма_ПП'].astype(str).str.replace(',', '.').astype(float)
    else:
        df['Сумма_ПП'] = 0.0
    if 'Назначение_платежа' in df.columns:
        df['Период_услуги'] = df['Назначение_платежа'].apply(extract_period)
    else:
        df['Период_услуги'] = None
    if 'СТГ_подсказка_ИСД' in df.columns:
        df['is_bezreestroviy'] = df['СТГ_подсказка_ИСД'].apply(
            lambda x: x in BEZREESTROVIY_ISD if pd.notna(x) else False
        )
    else:
        df['is_bezreestroviy'] = False
    return df

def group_applications(df):
    fixed_cols = ['ЦФО', 'Проект', 'Статья_оборотов', 'Вид_затрат',
              'СТГ_подсказка_ИСД', 'Код', 'Контрагент', 'Признак_оплаты',
              'Статус_согласования', 'Дата_последнего_статуса',
              'Замечания_ДФ', 'Состояние_заявки', 'Ответственный',
              'Оплачена', 'Дата_оплаты_фактич', 'Договор_код']
    fixed_cols = [c for c in fixed_cols if c in df.columns]
    agg_cols = {}
    for col in ['Договор_контрагента', 'Назначение_платежа', 'Номер_РП_чистый',
                'Платежное_поручение_исходящее', 'Документ_расчетов_с_контрагентом', 'Период_услуги']:
        if col in df.columns:
            agg_cols[col] = agg_text if col != 'Период_услуги' else agg_first
    agg_cols['Сумма_заявки'] = agg_sum
    agg_cols['Сумма_ПП'] = agg_sum
    agg_cols['is_bezreestroviy'] = agg_any

    grouped = df.groupby(['Номер_заявки', 'Дата_без_времени'], as_index=False).agg({
        **{c: agg_first for c in fixed_cols},
        **agg_cols
    })
    grouped.rename(columns={'Дата_без_времени': 'дата'}, inplace=True)
    if 'Оплачена' in grouped.columns:
        grouped['Оплачена'] = grouped['Оплачена'].fillna('Нет')
    else:
        grouped['Оплачена'] = 'Нет'
    if 'Номер_РП_чистый' in grouped.columns:
        grouped.rename(columns={'Номер_РП_чистый': 'Номер_РП'}, inplace=True)
    return grouped

def upsert_applications(df):
    df.columns = [c.lower() for c in df.columns]
    # Ищем именно столбец 'дата', чтобы не спутать с 'дата_оплаты_фактич'
    if 'дата' not in df.columns:
        # На случай, если дата пришла из 'Дата_без_времени'
        date_col = next((c for c in df.columns if c == 'дата' or c == 'date'), None)
        if date_col is None:
            raise KeyError("Столбец 'дата' не найден. Доступны: " + ", ".join(df.columns))
    else:
        date_col = 'дата'

    df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.date
    if 'дата_последнего_статуса' in df.columns:
        df['дата_последнего_статуса'] = pd.to_datetime(df['дата_последнего_статуса'], errors='coerce')

    # Обработка даты фактической оплаты
    if 'дата_оплаты_фактич' in df.columns:
        df['дата_оплаты_фактич'] = pd.to_datetime(df['дата_оплаты_фактич'], errors='coerce').dt.date

    # Переименование основного столбца с датой в 'дата' (если ещё не так)
    if date_col != 'дата':
        df.rename(columns={date_col: 'дата'}, inplace=True)

    all_columns = [
    'номер_заявки', 'дата', 'цфо', 'проект', 'статья_оборотов', 'вид_затрат',
    'стг_подсказка_исд', 'код', 'контрагент', 'признак_оплаты',
    'договор_контрагента', 'договор_код',
    'документ_расчетов_с_контрагентом',
    'назначение_платежа', 'номер_рп',
    'оплачена', 'платежное_поручение_исходящее', 'статус_согласования',
    'дата_последнего_статуса', 'замечания_дф', 'состояние_заявки',
    'ответственный', 'сумма_заявки', 'сумма_пп', 'период_услуги',
    'дата_оплаты_фактич', 'is_bezreestroviy'
    ]
    insert_cols = [c for c in all_columns if c in df.columns]
    for req in ['номер_заявки', 'дата', 'сумма_заявки']:
        if req not in insert_cols:
            raise KeyError(f"Обязательная колонка '{req}' отсутствует в DataFrame")

    temp_table = "applications_temp"
    df[insert_cols].to_sql(temp_table, engine, if_exists='replace', index=False, method='multi')

    col_list = ', '.join(insert_cols)
    update_set = ', '.join([f"{c} = EXCLUDED.{c}" for c in insert_cols if c not in ['номер_заявки', 'дата']])
    conflict_cols = 'номер_заявки, дата'

    upsert_sql = f"""
    INSERT INTO applications ({col_list})
    SELECT {col_list} FROM {temp_table}
    ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_set};
    DROP TABLE {temp_table};
    """
    with engine.connect() as conn:
        conn.execute(text(upsert_sql))
        conn.commit()

def load_and_clean_registers(file_path):
    xls = pd.ExcelFile(file_path)
    if 'Sheet1' in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name='Sheet1', dtype=str)
    else:
        df = pd.read_excel(file_path, sheet_name=xls.sheet_names[0], dtype=str)
    df = df[~df['№ Реестра платежей'].astype(str).str.contains('удалить', case=False, na=False)].copy()
    df.columns = df.columns.str.strip().str.replace(' ', '_')
    mapping_reg = {
        '№_Реестра_платежей': 'номер_реестра_исходный',
        'ИСД': 'исд',
        'ID_заявки': 'id_заявки',
        'Дата_Реестра_платежей': 'дата_реестра',
        'Дата_отправки_на_согласование': 'дата_отправки',
        'Дата_поступления_на_согласование_КСД': 'дата_поступления_ксд',
        'Дата_поступления_на_согласование_КД': 'дата_поступления_кд',
        'Дата_поступления_на_согласование_КБС': 'дата_поступления_кбс',
        'Дата_принятия_Банком': 'дата_принятия_банком',
        'Реестр_зарплатных_и_налоговых_платежей': 'реестр_зарплатных',
        'Вид_реестра_платежей': 'вид_реестра',
        'Тип_затрат': 'тип_затрат',
        'Тип_платежей': 'тип_платежей',
        'Инициатор': 'инициатор',
        'Наименование_инициатора': 'наименование_инициатора',
        'Наименование_плательщика': 'наименование_плательщика',
        'Получатель': 'получатель',
        'Подал_КСД': 'подал_ксд',
        'Факт_исполнения,_руб.': 'факт_исполнения',
        'Итоговая_сумма_заявленная,_руб.': 'сумма_заявленная',
        'Итоговая_сумма_согласованная,_руб.': 'сумма_согласованная',
        'Статус': 'статус',
        'Дополнительный_статус': 'дополнительный_статус'
    }
    df = rename_columns_by_pattern(df, mapping_reg)
    if 'номер_реестра_исходный' not in df.columns:
        raise KeyError(f"Столбец '№ Реестра платежей' не найден. Доступны: {list(df.columns)}")
    df['номер_реестра'] = df['номер_реестра_исходный'].apply(clean_register_number)
    date_cols = ['дата_реестра', 'дата_отправки', 'дата_поступления_ксд',
                 'дата_поступления_кд', 'дата_поступления_кбс', 'дата_принятия_банком']
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(normalize_date)
    num_cols = ['факт_исполнения', 'сумма_заявленная', 'сумма_согласованная']
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(',', '.').str.replace(' ', '').astype(float)
        else:
            df[col] = 0.0
    df = df[df['номер_реестра'].notna() & (df['номер_реестра'] != '')]
    return df

def upsert_registers(df):
    df.columns = [c.lower() for c in df.columns]
    date_cols = ['дата_реестра', 'дата_отправки', 'дата_поступления_ксд',
                 'дата_поступления_кд', 'дата_поступления_кбс', 'дата_принятия_банком']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    df = df[df['номер_реестра'].notna() & (df['номер_реестра'] != '')]
    df = df.groupby('номер_реестра', as_index=False).first()

    all_columns = [
        'номер_реестра', 'номер_реестра_исходный', 'дата_реестра', 'дата_отправки',
        'дата_поступления_ксд', 'дата_поступления_кд', 'дата_поступления_кбс',
        'дата_принятия_банком', 'реестр_зарплатных', 'вид_реестра',
        'тип_затрат', 'тип_платежей', 'инициатор', 'наименование_инициатора',
        'наименование_плательщика', 'получатель', 'подал_ксд',
        'факт_исполнения', 'сумма_заявленная', 'сумма_согласованная',
        'статус', 'дополнительный_статус', 'id_заявки', 'исд'
    ]
    insert_cols = [c for c in all_columns if c in df.columns]
    if 'номер_реестра' not in insert_cols:
        raise KeyError("Колонка 'номер_реестра' отсутствует в DataFrame")

    temp_table = "registers_temp"
    df[insert_cols].to_sql(temp_table, engine, if_exists='replace', index=False, method='multi')

    col_list = ', '.join(insert_cols)
    update_set = ', '.join([f"{c} = EXCLUDED.{c}" for c in insert_cols if c != 'номер_реестра'])
    upsert_sql = f"""
    INSERT INTO registers ({col_list})
    SELECT {col_list} FROM {temp_table}
    ON CONFLICT (номер_реестра) DO UPDATE SET {update_set};
    DROP TABLE {temp_table};
    """
    with engine.connect() as conn:
        conn.execute(text(upsert_sql))
        conn.commit()