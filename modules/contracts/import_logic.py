import pandas as pd
from datetime import date
from modules.core.utils import parse_date_dd_mm_yyyy, clean_money

def should_skip(row):
    # Правило 1
    if str(row.get('Рамочный', '')).strip().lower() == 'да' and \
       str(row.get('Контроль по спецификациям', '')).strip().lower() == 'да':
        return True
    # Правило 2
    if str(row.get('Счет(оферта)', '')).strip().lower() == 'да' and \
       parse_date_dd_mm_yyyy(str(row.get('Дата', ''))) < date(2026, 1, 1):
        return True
    # Правило 3
    if str(row.get('Без финансовых обязательств', '')).strip().lower() == 'да':
        return True
    # Правило 4
    char = str(row.get('Характер договора', '')).strip()
    if char in (
        'Прочие договоры',
        'Уступки прав требования'
        'Платежи в бюджет ( госпошлина, лицензии и т.д.)',
        'Приобретение/отчуждение прав на объекты интеллектуальной собственности'
	):
        return True
    return False

def load_and_clean_contracts(file_path):
    # Читаем Excel-файл (первый лист), все ячейки как строки
    df = pd.read_excel(file_path, sheet_name=0, dtype=str)
    
    # Отбираем только "Да" в 'Выгружать в ДО' (если такого столбца нет – не фильтруем)
    #if 'Выгружать в ДО' in df.columns:
    #    df = df[df['Выгружать в ДО'].str.strip().str.lower() == 'да']
    
    # Применяем кастомные правила исключения
    mask = df.apply(should_skip, axis=1)
    df = df[~mask]

    # Извлечение нужных полей
    contracts = pd.DataFrame()
    contracts['contract_number'] = df.get('Номер', '')
    contracts['counterparty'] = df.get('Контрагент', '')
    contracts['inn'] = df.get('ИНН Контрагента', '')
    contracts['amount'] = df.get('Сумма договора', '0').apply(clean_money)
    contracts['start_date'] = df.get('Дата возникновения обязательств', df.get('Дата')).apply(parse_date_dd_mm_yyyy)
    def get_end_date(row):
        return parse_date_dd_mm_yyyy(row.get('Дата погашения обязательств', ''))
        #end = parse_date_dd_mm_yyyy(row.get('Дата погашения обязательств', ''))
        #if end: return end
        #until = str(row.get('Действует до', '')).strip()
        #end2 = parse_date_dd_mm_yyyy(until)
        #if end2: return end2
        #return None
    contracts['end_date'] = df.apply(get_end_date, axis=1)
    contracts['условия_пролонгации'] = df.get('Условия_пролонгации', '')
    contracts['status'] = df.get('Статус действия', '')
    contracts['matching_text'] = df.get('Договор/Сделка', '').str.lower()
    contracts['is_frame'] = df.get('Рамочный', 'Нет').str.strip().str.lower() == 'да'
    contracts['external_code'] = df.get('Код', '')
    contracts['цфо'] = df.get('Ответственное_подразделение', '')

    # Удаляем строки, где matching_text пустой (нет связи)
    contracts = contracts[contracts['matching_text'].notna() & (contracts['matching_text'] != '')]
    return contracts

def _upsert_contracts(engine, df):
    from sqlalchemy import text
    temp_table = 'contracts_temp'
    df.to_sql(temp_table, engine, if_exists='replace', index=False)
    with engine.connect() as conn:
        conn.execute(text(f"""
        INSERT INTO contracts (contract_number, counterparty, inn, amount, start_date, end_date, status, matching_text, is_frame, external_code, ответственный, цфо)
        SELECT contract_number, counterparty, inn, amount, start_date, end_date, status, matching_text, is_frame, external_code, ответственный, цфо
        FROM {temp_table}
        ON CONFLICT (external_code) DO UPDATE SET
            contract_number = EXCLUDED.contract_number,
            counterparty = EXCLUDED.counterparty,
            inn = EXCLUDED.inn,
            amount = EXCLUDED.amount,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            status = EXCLUDED.status,
            matching_text = EXCLUDED.matching_text,
            is_frame = EXCLUDED.is_frame,
            ответственный = EXCLUDED.ответственный,
            цфо = EXCLUDED.цфо;
        """))
        conn.execute(text(f"DROP TABLE {temp_table};"))
        conn.commit()
def upsert_contracts(engine, df):
    from sqlalchemy import text

    # На всякий случай убираем столбец ответственный, если он случайно попал в df
    if 'ответственный' in df.columns:
        df = df.drop(columns=['ответственный'])

    temp_table = 'contracts_temp'
    df.to_sql(temp_table, engine, if_exists='replace', index=False)

    with engine.connect() as conn:
        conn.execute(text(f"""
        INSERT INTO contracts (
            contract_number, counterparty, inn, amount,
            start_date, end_date, status, matching_text, is_frame,
            external_code, цфо, условия_пролонгации
        )
        SELECT
            contract_number, counterparty, inn, amount,
            start_date, end_date, status, matching_text, is_frame,
            external_code, цфо, условия_пролонгации
        FROM {temp_table}
        ON CONFLICT (external_code) DO UPDATE SET
            contract_number = EXCLUDED.contract_number,
            counterparty = EXCLUDED.counterparty,
            inn = EXCLUDED.inn,
            amount = EXCLUDED.amount,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            status = EXCLUDED.status,
            matching_text = EXCLUDED.matching_text,
            is_frame = EXCLUDED.is_frame,
            цфо = EXCLUDED.цфо,
            условия_пролонгации = EXCLUDED.условия_пролонгации;
        """))
        conn.execute(text(f"DROP TABLE {temp_table};"))
        conn.commit()