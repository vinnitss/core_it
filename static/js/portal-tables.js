/**
 * Единый хелпер для инициализации таблиц портала.
 *
 * Использование:
 *   portalTable('#myTable', { order: [[0, 'desc']] });
 *
 * Все таблицы получают:
 * - одинаковый язык (русский)
 * - выпадающий список страниц
 * - адаптивное поведение (сворачивание колонок)
 * - поиск по всем столбцам
 */
function portalTable(selector, options = {}) {
    if (!$(selector).length) return null;

    const defaults = {
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'Все']],
        language: {
            url: '//cdn.datatables.net/plug-ins/1.13.6/i18n/ru.json'
        },
        autoWidth: false,
        responsive: false,
        stateSave: true,            // запоминает фильтры/страницу/сортировку
        stateDuration: 60 * 60 * 24, // 24 часа
        columnDefs: [
            { targets: 'no-sort', orderable: false }
        ]
    };

    return $(selector).DataTable(Object.assign({}, defaults, options));
}

/**
 * Инициализация по умолчанию для всех таблиц с классом .portal-table[data-table]
 * Автоматически подхватывает параметры из data-атрибутов:
 *   data-table="true"       — включить DataTables
 *   data-order-col="3"      — колонка сортировки по умолчанию
 *   data-order-dir="desc"   — направление
 */
$(document).ready(function () {
    $('table.portal-table[data-table]').each(function () {
        const $t = $(this);
        if ($.fn.DataTable.isDataTable($t)) return;

        const orderCol = parseInt($t.data('order-col'), 10);
        const orderDir = $t.data('order-dir') || 'asc';

        const options = {};
        if (!isNaN(orderCol)) {
            options.order = [[orderCol, orderDir]];
        }
        portalTable($t, options);
    });
});