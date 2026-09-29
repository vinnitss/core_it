"""
Метаданные для конструктора отчётов.
Описание источников данных, полей и операторов.
"""

DATA_SOURCES = {
    'v_applications_full': {
        'label': 'Заявки',
        'cfo_field': 'цфо',
        'default_date_field': 'дата',
        'fields': [
            {'name': 'номер_заявки', 'label': 'Номер заявки', 'type': 'string'},
            {'name': 'дата', 'label': 'Дата', 'type': 'date'},
            {'name': 'цфо', 'label': 'ЦФО', 'type': 'string'},
            {'name': 'проект', 'label': 'Проект', 'type': 'string'},
            {'name': 'контрагент', 'label': 'Контрагент', 'type': 'string'},
            {'name': 'код', 'label': 'Код проекта', 'type': 'string'},
            {'name': 'сумма_заявки', 'label': 'Сумма заявки', 'type': 'number'},
            {'name': 'сумма_пп', 'label': 'Сумма ПП', 'type': 'number'},
            {'name': 'оплачена', 'label': 'Оплачена', 'type': 'string'},
            {'name': 'статус_согласования', 'label': 'Статус согласования', 'type': 'string'},
            {'name': 'состояние_заявки', 'label': 'Состояние заявки', 'type': 'string'},
            {'name': 'итоговый_статус_реестра', 'label': 'Статус реестра', 'type': 'string'},
            {'name': 'период_услуги', 'label': 'Период услуги', 'type': 'date'},
            {'name': 'ответственный', 'label': 'Ответственный', 'type': 'string'},
            {'name': 'договор_контрагента', 'label': 'Договор контрагента', 'type': 'string'},
            {'name': 'договор_код', 'label': 'Код договора', 'type': 'string'},
            {'name': 'назначение_платежа', 'label': 'Назначение платежа', 'type': 'string'},
            {'name': 'признак_оплаты', 'label': 'Признак оплаты', 'type': 'string'},
            {'name': 'дата_оплаты_фактич', 'label': 'Дата оплаты фактическая', 'type': 'date'},
        ],
    },
    'contracts': {
        'label': 'Договоры',
        'cfo_field': 'цфо',
        'default_date_field': 'start_date',
        'fields': [
            {'name': 'external_code', 'label': 'Внешний код', 'type': 'string'},
            {'name': 'contract_number', 'label': 'Номер договора', 'type': 'string'},
            {'name': 'counterparty', 'label': 'Контрагент', 'type': 'string'},
            {'name': 'inn', 'label': 'ИНН', 'type': 'string'},
            {'name': 'amount', 'label': 'Сумма договора', 'type': 'number'},
            {'name': 'start_date', 'label': 'Дата начала', 'type': 'date'},
            {'name': 'end_date', 'label': 'Дата окончания', 'type': 'date'},
            {'name': 'status', 'label': 'Статус', 'type': 'string'},
            {'name': 'ответственный', 'label': 'Ответственный', 'type': 'string'},
            {'name': 'цфо', 'label': 'ЦФО', 'type': 'string'},
            {'name': 'условия_пролонгации', 'label': 'Условия пролонгации', 'type': 'string'},
        ],
    },
    'debts': {
        'label': 'Задолженность',
        'cfo_field': 'цфо',
        'default_date_field': 'дата_документа',
        'fields': [
            {'name': 'вид_задолженности', 'label': 'Вид', 'type': 'string'},
            {'name': 'счет', 'label': 'Счёт', 'type': 'string'},
            {'name': 'контрагент', 'label': 'Контрагент', 'type': 'string'},
            {'name': 'инн', 'label': 'ИНН', 'type': 'string'},
            {'name': 'договор_код', 'label': 'Код договора', 'type': 'string'},
            {'name': 'договор_наименование', 'label': 'Наименование договора', 'type': 'string'},
            {'name': 'проект', 'label': 'Проект', 'type': 'string'},
            {'name': 'цфо', 'label': 'ЦФО', 'type': 'string'},
            {'name': 'номер_документа', 'label': 'Номер документа', 'type': 'string'},
            {'name': 'дата_документа', 'label': 'Дата документа', 'type': 'date'},
            {'name': 'документ_расчетов', 'label': 'Документ расчётов', 'type': 'string'},
            {'name': 'период_погашения', 'label': 'Период погашения', 'type': 'date'},
            {'name': 'дней_просрочки', 'label': 'Дней просрочки', 'type': 'number'},
            {'name': 'сумма_остаток', 'label': 'Сумма остаток', 'type': 'number'},
        ],
    },
    'v_registers': {
        'label': 'Реестры платежей',
        'cfo_field': None,   # Реестры общие
        'default_date_field': 'дата_реестра',
        'fields': [
            {'name': 'номер_реестра', 'label': 'Номер реестра', 'type': 'string'},
            {'name': 'сумма_согласованная', 'label': 'Сумма согласованная', 'type': 'number'},
            {'name': 'вычисленный_статус', 'label': 'Статус', 'type': 'string'},
            {'name': 'дата_реестра', 'label': 'Дата реестра', 'type': 'date'},
            {'name': 'статус', 'label': 'Статус (банк)', 'type': 'string'},
            {'name': 'дополнительный_статус', 'label': 'Доп. статус', 'type': 'string'},
        ],
    },
}


OPERATORS = {
    'string': [
        {'value': 'eq', 'label': 'Равно'},
        {'value': 'neq', 'label': 'Не равно'},
        {'value': 'contains', 'label': 'Содержит'},
        {'value': 'not_contains', 'label': 'Не содержит'},
        {'value': 'is_null', 'label': 'Пусто'},
        {'value': 'not_null', 'label': 'Не пусто'},
    ],
    'number': [
        {'value': 'eq', 'label': 'Равно'},
        {'value': 'neq', 'label': 'Не равно'},
        {'value': 'gt', 'label': 'Больше'},
        {'value': 'gte', 'label': 'Больше или равно'},
        {'value': 'lt', 'label': 'Меньше'},
        {'value': 'lte', 'label': 'Меньше или равно'},
        {'value': 'between', 'label': 'Между'},
    ],
    'date': [
        {'value': 'eq', 'label': 'Равно'},
        {'value': 'gt', 'label': 'После'},
        {'value': 'gte', 'label': 'Начиная с'},
        {'value': 'lt', 'label': 'До'},
        {'value': 'lte', 'label': 'По'},
        {'value': 'between', 'label': 'Между'},
        {'value': 'is_null', 'label': 'Пусто'},
        {'value': 'not_null', 'label': 'Не пусто'},
    ],
}


AGGREGATIONS = [
    {'value': 'sum', 'label': 'Сумма'},
    {'value': 'count', 'label': 'Количество'},
    {'value': 'avg', 'label': 'Среднее'},
    {'value': 'min', 'label': 'Минимум'},
    {'value': 'max', 'label': 'Максимум'},
]