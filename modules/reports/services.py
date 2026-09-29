import pandas as pd
from modules.core.utils import current_cfo, read_sql


def get_data(view='quick', filters=None):
    cfo = current_cfo()
    cfo_sql = "AND цфо = %(user_cfo)s" if cfo else ""
    cfo_params = {'user_cfo': cfo} if cfo else {}

    if view == 'quick':
        query = f"""
        SELECT 
            номер_заявки,
            стг_подсказка_исд,
            проект,
            контрагент,
            сумма_заявки,
            номер_рп AS номер_реестра,
            CASE 
                WHEN is_bezreestroviy = TRUE 
                    AND итоговый_статус_реестра IS NULL 
                    THEN 'Безреестровый'
                ELSE итоговый_статус_реестра
            END AS итоговый_статус_реестра,
            статус_согласования,
            период_услуги,
            ответственный,
            назначение_платежа,
            договор_контрагента
        FROM v_applications_full
        WHERE оплачена = 'Нет'
          AND статус_согласования IN ('Согласовано ДФ', 'Согласовано руководителем ЦФО')
          AND (состояние_заявки IS NULL 
               OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
          AND (
              код IN ('СТГ-00', 'СТГ-2011-ОРГ', 'СТНГ-ПВД')
              OR is_bezreestroviy = TRUE
              OR итоговый_статус_реестра = 'На согласовании'
              OR итоговый_статус_реестра ILIKE '%%Принят%%анком%%'
          )
          {cfo_sql}
        """
        return read_sql(query, params=cfo_params)

    elif view == 'pay_cal':
        # Новый отчёт: те же условия, но статус реестра обязательно заполнен.
        # Безреестровые сюда не попадают — у них итоговый_статус_реестра = NULL.
        query = f"""
        SELECT 
            номер_заявки,
            стг_подсказка_исд,
            проект,
            контрагент,
            сумма_заявки,
            номер_рп AS номер_реестра,
            CASE 
                WHEN is_bezreestroviy = TRUE 
                    AND итоговый_статус_реестра IS NULL 
                    THEN 'Безреестровый'
                ELSE итоговый_статус_реестра
            END AS итоговый_статус_реестра,
            статус_согласования,
            период_услуги,
            ответственный,
            назначение_платежа,
            договор_контрагента
        FROM v_applications_full
        WHERE оплачена = 'Нет'
          AND статус_согласования IN ('Согласовано ДФ', 'Согласовано руководителем ЦФО')
          AND (состояние_заявки IS NULL 
               OR состояние_заявки NOT IN ('Аннулирован', 'Подготовлен'))
          AND (
              код IN ('СТГ-00', 'СТГ-2011-ОРГ', 'СТНГ-ПВД')
              OR is_bezreestroviy = TRUE
              OR итоговый_статус_реестра = 'Возвращена на доработку'
              OR итоговый_статус_реестра = 'На согласовании'
              OR итоговый_статус_реестра = 'На согласовании у Исполнителя'             
              OR итоговый_статус_реестра ILIKE '%%Принят%%анком%%'
          )
          {cfo_sql}
        ORDER BY период_услуги DESC NULLS LAST, номер_заявки DESC
        """
        return read_sql(query, params=cfo_params)

    elif view == 'full':
        query = """
        SELECT *
        FROM v_applications_full
        WHERE 1=1
        """
        params = dict(cfo_params)
        if cfo:
            query += " AND цфо = %(user_cfo)s"
        if filters:
            if filters.get('проект'):
                query += " AND проект = %(проект)s"
                params['проект'] = filters['проект']
            if filters.get('контрагент'):
                query += " AND контрагент ILIKE %(контрагент)s"
                params['контрагент'] = f'%{filters["контрагент"]}%'
            if filters.get('статус_реестра'):
                query += " AND итоговый_статус_реестра = %(статус_реестра)s"
                params['статус_реестра'] = filters['статус_реестра']
            if filters.get('статус_согласования'):
                query += " AND статус_согласования = %(статус_согласования)s"
                params['статус_согласования'] = filters['статус_согласования']
            if filters.get('оплачена'):
                query += " AND оплачена = %(оплачена)s"
                params['оплачена'] = filters['оплачена']
            if filters.get('дата_от') and filters.get('дата_до'):
                query += " AND период_услуги BETWEEN %(дата_от)s AND %(дата_до)s"
                params['дата_от'] = filters['дата_от']
                params['дата_до'] = filters['дата_до']
        return read_sql(query, params=params)

    elif view == 'registers':
        # Реестры — общие, не фильтруем по ЦФО
        query = """
        SELECT 
            номер_реестра,
            сумма_согласованная,
            вычисленный_статус,
            дата_реестра,
            статус,
            дополнительный_статус
        FROM v_registers
        WHERE 1=1
        """
        params = {}
        if filters:
            if filters.get('статус_реестра'):
                query += " AND вычисленный_статус = %(статус_реестра)s"
                params['статус_реестра'] = filters['статус_реестра']
            if filters.get('дата_от') and filters.get('дата_до'):
                query += " AND дата_реестра BETWEEN %(дата_от)s AND %(дата_до)s"
                params['дата_от'] = filters['дата_от']
                params['дата_до'] = filters['дата_до']
        return read_sql(query, params=params)

    return pd.DataFrame()


def get_filter_options(view='quick'):
    cfo = current_cfo()
    cfo_sql = " AND цфо = %(cfo)s" if cfo else ""
    cfo_params = {'cfo': cfo} if cfo else {}

    if view in ('quick', 'pay_cal'):
        return [], [], [], []

    elif view == 'full':
        if cfo_params:
            projects = read_sql(
                f"SELECT DISTINCT проект FROM v_applications_full WHERE 1=1 {cfo_sql} ORDER BY проект",
                params=cfo_params
            )['проект'].tolist()
            statuses = read_sql(
                f"SELECT DISTINCT итоговый_статус_реестра FROM v_applications_full WHERE 1=1 {cfo_sql} ORDER BY итоговый_статус_реестра",
                params=cfo_params
            )['итоговый_статус_реестра'].tolist()
            approval_statuses = read_sql(
                f"SELECT DISTINCT статус_согласования FROM v_applications_full WHERE 1=1 {cfo_sql} ORDER BY статус_согласования",
                params=cfo_params
            )['статус_согласования'].tolist()
        else:
            projects = read_sql(
                "SELECT DISTINCT проект FROM v_applications_full WHERE 1=1 ORDER BY проект"
            )['проект'].tolist()
            statuses = read_sql(
                "SELECT DISTINCT итоговый_статус_реестра FROM v_applications_full WHERE 1=1 ORDER BY итоговый_статус_реестра"
            )['итоговый_статус_реестра'].tolist()
            approval_statuses = read_sql(
                "SELECT DISTINCT статус_согласования FROM v_applications_full WHERE 1=1 ORDER BY статус_согласования"
            )['статус_согласования'].tolist()

        paid_options = ['Да', 'Нет']
        return projects, statuses, approval_statuses, paid_options

    elif view == 'registers':
        statuses = read_sql(
            "SELECT DISTINCT вычисленный_статус FROM v_registers ORDER BY вычисленный_статус"
        )['вычисленный_статус'].tolist()
        return [], statuses, [], []

    return [], [], [], []