# Руководство администратора

Техническое руководство по развёртыванию, обновлению и сопровождению портала.
Доступно только пользователям с ролью **admin**.

## Содержание

1. [Архитектура](#архитектура)
2. [Развёртывание](#развёртывание)
3. [Конфигурация](#конфигурация)
4. [Обновление портала](#обновление-портала)
5. [Управление пользователями](#управление-пользователями)
6. [Управление импортом](#управление-импортом)
7. [Модуль объектов](#модуль-объектов)
8. [Матчинг заявок к объектам](#матчинг-заявок-к-объектам)
9. [Персональные дашборды](#персональные-дашборды)
10. [Персонализация sidebar](#персонализация-sidebar)
11. [Диагностика](#диагностика)
12. [Nginx и SSL](#nginx-и-ssl)
13. [Структура базы данных](#структура-базы-данных)
14. [Логика вычислений](#логика-вычислений)
15. [Частые проблемы](#частые-проблемы)

---

## Архитектура

```
┌──────────────┐
│  Пользователь│
└──────┬───────┘
       │ HTTPS
       ▼
┌──────────────┐
│    Nginx     │  ← reverse proxy + SSL
└──────┬───────┘
       │ HTTP (127.0.0.1:5000)
       ▼
┌──────────────────────┐      ┌─────────────────┐
│  Flask + Gunicorn    │─────▶│  PostgreSQL 15  │
│  (в контейнере app)  │      │ (в контейнере db)│
└──────────────────────┘      └─────────────────┘
```

### Каталоги

```
~/core_it/
├── app.py              # точка входа Flask
├── config.py           # центральный конфиг
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env                # секреты
├── create_admin.py     # создание первого админа
├── modules/
│   ├── core/           # engine, утилиты, sidebar
│   │   ├── utils.py
│   │   ├── logging_config.py
│   │   ├── sidebar.py
│   │   └── sidebar_routes.py
│   ├── auth/           # аутентификация
│   ├── admin/          # управление пользователями
│   ├── home/           # главная
│   ├── reports/        # быстрый отчёт
│   ├── dashboard/      # дашборды + виджеты + мой дашборд
│   │   ├── routes.py
│   │   ├── services.py
│   │   ├── widgets.py       # реестр виджетов
│   │   └── user_dashboard.py # сервис личного дашборда
│   ├── contracts/      # договоры + расчёты + импорт договоров
│   ├── debts/          # задолженность (только импорт + редиректы)
│   ├── import_data/    # импорт заявок и реестров
│   ├── objects/        # справочник объектов + токены + матчинг
│   ├── report_builder/ # конструктор отчётов
│   └── help/           # справка
├── templates/
├── static/
├── docs/               # markdown-документация
└── logs/               # логи приложения
```

---

## Развёртывание

### Требования

- Ubuntu 22.04 или 24.04
- Docker 24+ и Docker Compose v2
- 2 ГБ RAM, 10 ГБ диска
- Открытый порт 80 (и 443 для HTTPS)

### Установка Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# После этого перелогиньтесь
```

### Подготовка окружения

```bash
mkdir -p ~/core_it && cd ~/core_it
# Скопируйте сюда все файлы проекта
```

Создайте `.env`:

```env
POSTGRES_USER=report_user
POSTGRES_PASSWORD=<надёжный_пароль>
POSTGRES_DB=report_db
PGDATA=/var/lib/postgresql/data/pgdata

SECRET_KEY=<случайная_строка_не_короче_32_символов>
DATABASE_URL=postgresql://report_user:<надёжный_пароль>@db:5432/report_db

LOG_LEVEL=INFO
SLOW_QUERY_THRESHOLD=3.0
SESSION_LIFETIME_HOURS=8
SESSION_COOKIE_SECURE=false
```

### Запуск

```bash
cd ~/core_it
docker compose up -d --build
```

### Первый вход

```bash
docker compose cp create_admin.py app:/app/create_admin.py
docker compose exec app python3 create_admin.py admin@stng.ru <временный_пароль>
```

Откройте портал, войдите под этим админом, смените пароль.

---

## Конфигурация

Все настройки — в файле `config.py`, читающем переменные окружения.

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `DATABASE_URL` | Подключение к БД | обязательно |
| `SECRET_KEY` | Ключ сессии | обязательно |
| `MAX_CONTENT_LENGTH` | Лимит файла при импорте | 200 МБ |
| `LOG_LEVEL` | Уровень логирования | INFO |
| `LOG_FILE` | Путь к файлу логов | /app/logs/app.log |
| `SLOW_QUERY_THRESHOLD` | Порог медленных запросов (сек) | 3.0 |
| `SESSION_LIFETIME_HOURS` | Время жизни сессии | 8 |
| `SESSION_COOKIE_SECURE` | Secure-флаг cookie (true при HTTPS) | false |

### Изменение конфигурации

1. Отредактируйте `.env` (или `config.py`).
2. Перезапустите: `docker compose restart app`.

---

## Обновление портала

### Обновление кода

Если папки смонтированы как volumes (стандартная конфигурация):

```bash
cd ~/core_it
git pull                  # или скопируйте новые файлы
docker compose restart app
```

Изменения в `modules/` и `templates/` подхватятся автоматически.

### Если менялся `requirements.txt` или `Dockerfile`

```bash
docker compose down
docker compose build --no-cache app
docker compose up -d
```

### Если менялась схема БД

Схема обновляется автоматически при старте приложения через
`create_all_tables()` + `ALTER TABLE IF NOT EXISTS`. Никаких ручных
действий не требуется.

---

## Управление пользователями

**Где:** Администрирование → Пользователи.

### Роли

| Роль | Что может |
|---|---|
| **admin** | Всё. Видит всех пользователей и все данные |
| **manager** | Просмотр своих данных + импорт (если `can_import`) |
| **viewer** | Только просмотр своих данных |

### Возможности

- **Создать пользователя** — email, временный пароль, роль, ЦФО.
- **Редактировать** — роль, ЦФО, флаг импорта, активность.
- **Сбросить пароль** — задать новый временный.
- **Деактивировать** — пользователь не может войти.
- **Сбросить настройки sidebar** — вернуть дефолтное меню (планируется).

### Признак ЦФО

Если у пользователя заполнен ЦФО — он видит только данные своего
подразделения во всех аналитических разделах. Реестры платежей — общие.

### Первый администратор

Создаётся вручную через `create_admin.py`. Дальше создаются через UI.

---

## Управление импортом

**Где:** Сервис → Импорт.

### Права

Импортировать могут:
- пользователи с ролью **admin**;
- пользователи с флагом **can_import**.

### Механика

Форма отправляется через **AJAX**. Пока идёт обработка, отображается
оверлей с прогресс-баром и секундомером. По завершении — зелёное или
красное уведомление.

### Правила импорта

| Файл | Логика |
|---|---|
| **Заявки** | Группировка по `номер + дата`, upsert |
| **Реестры** | Upsert по номеру реестра |
| **Договоры** | Фильтрация, upsert по external_code, пересборка связей, ответственных и ЦФО |
| **Задолженность** | Полная очистка + загрузка |

### Что происходит после импорта

1. Заявки, реестры, договоры — обновляются с сохранением существующих.
2. Задолженность — **полностью заменяется**.
3. Связи заявка ↔ договор — пересобираются по полю `договор_код`.
4. Ответственные и ЦФО в договорах — вычисляются по заявкам.

### Диагностика импорта

Логи:

```bash
docker compose logs -f app | grep -E "IMPORT|Link"
```

Ключевые строки:
- `IMPORT RESULT: [...]` — успешный импорт.
- `IMPORT ERROR: ...` — ошибка.
- `Link: связей создано N` — результат привязки.
- `SLOW QUERY: ...` — медленные запросы.

---

## Модуль объектов

**Где:** Объекты (в основном sidebar).

### Структура таблицы `objects`

| Поле | Тип | Описание |
|---|---|---|
| `id` | SERIAL | Первичный ключ |
| `code` | TEXT UNIQUE | 3-значный код для заявок |
| `name` | TEXT | Полное название |
| `sname` | TEXT | Краткое название |
| `type` | TEXT | `res` / `site` / `office` |
| `status` | TEXT | `active` / `delayed` / `stopped` |
| `project` | TEXT | Проект |
| `field` | TEXT | Месторождение (справочно) |
| `city` | TEXT | Ближайший крупный город |
| `lat`, `lon` | NUMERIC | Координаты |
| `responsible` | TEXT | Ответственный |
| `info` | TEXT | Описание для карты |

### Импорт объектов

**Где:** Объекты → кнопка «Загрузить CSV» (только для админа).

**Формат CSV:**

```csv
code;name;sname;type;status;project;field;city;lat;lon;responsible;info
001;ВЗиС 105км ЧНГКМ;ВЗиС 105км;res;active;Проект X;ЧНГКМ;Южно-Сахалинск;60.3654;111.4220;Иванов И.И.;Описание
```

- Разделитель — `;`.
- Кодировка — UTF-8 или cp1251.
- Порядок столбцов не важен.
- Upsert по `code`.

### Присвоение кодов

Если у объектов нет кодов — кнопка «Присвоить коды» раздаёт `001`, `002` и т.д. Учитывает максимальный существующий.

### Карта объектов

Использует Leaflet + OpenStreetMap. Для отображения нужен доступ в интернет
к `unpkg.com` и `tile.openstreetmap.org`. Если есть ограничения — скачайте
библиотеки локально в `static/`.

---

## Матчинг заявок к объектам

**Где:** Администрирование → Проверка матчей.

### Как работает

1. Из названий объектов извлекаются токены (`build_object_tokens`).
2. Для каждой заявки текст (`назначение_платежа` + `договор_контрагента`)
   токенизируется.
3. Считается совпадение токенов и score.
4. Присваивается уровень уверенности.

### Уровни уверенности

| Уровень | Условие | Действие |
|---|---|---|
| **HIGH** | score ≥ 1.5 (даже 1 токен) или несколько специфичных | auto-confirm |
| **MEDIUM** | score ≥ 0.8 | auto-confirm |
| **AMBIGUOUS** | несколько равных кандидатов | требует ручного выбора |
| **LOW** | score < 0.8 | не присваивается |
| **NO_MATCH** | нет совпадений | — |

### Запуск

1. Откройте **Проверка матчей** → кнопка «Пересчитать матчи».
2. Дождитесь завершения — статистика обновится.

### API-функции (для ручного вызова)

```bash
docker compose exec app python3 -c "
from modules.objects.matching import build_object_tokens, save_matches
build_object_tokens()   # обновляет токены объектов
result = save_matches() # пересчитывает матчи и сохраняет
print(result)
"
```

### Ручная проверка

- **Список** — фильтры по уровню, проекту, поиску.
- **Карточка** — кандидаты с score, выбор объекта вручную, кнопки
  «Подтвердить» / «Отклонить».

### Столбцы в `applications` для матчей

| Поле | Что содержит |
|---|---|
| `object_id` | ID присвоенного объекта |
| `object_match_confidence` | Уровень уверенности / CONFIRMED / REJECTED |
| `object_match_candidates` | JSONB со списком кандидатов |

---

## Персональные дашборды

**Где:** Мой дашборд.

### Структура таблицы `user_dashboards`

| Поле | Тип | Описание |
|---|---|---|
| `user_id` | INTEGER UNIQUE | Владелец |
| `widgets` | JSONB | Список виджетов |
| `is_default` | BOOLEAN | Используется ли стандартный набор |
| `updated_at` | TIMESTAMP | Дата последнего изменения |

### Формат `widgets`

```json
[
  {"key": "kpi_kz", "size": "small"},
  {"key": "chart_payments", "size": "full"}
]
```

### Реестр виджетов

Файл `modules/dashboard/widgets.py`. Каждый виджет:

```python
'kpi_kz': {
    'name': 'Кредиторская задолженность',
    'category': 'Задолженность',
    'type': 'kpi',          # kpi / table / chart
    'default_size': 'small',
    'service': 'get_kpi_kz',
}
```

### Как добавить новый виджет

1. Откройте `modules/dashboard/widgets.py`.
2. Добавьте запись в `WIDGETS`.
3. Напишите функцию-сервис с тем же именем, что в `service`.
4. Функция возвращает:
   - KPI: `{'value', 'label', 'color', 'icon', 'format'}`.
   - Таблица: `{'columns', 'rows', 'empty'}`.
   - График: `{'type', 'labels', 'datasets', 'empty'}`.
5. Перезапустите приложение — виджет появится в каталоге.

### API-эндпоинты

| Метод | URL | Что делает |
|---|---|---|
| GET | `/dashboard/my` | Страница дашборда |
| POST | `/dashboard/api/widgets/add` | Добавить виджет |
| POST | `/dashboard/api/widgets/remove` | Удалить виджет |
| POST | `/dashboard/api/widgets/reorder` | Изменить порядок |
| POST | `/dashboard/api/widgets/resize` | Изменить размер |
| POST | `/dashboard/api/widgets/reset` | Сбросить к стандарту |

### Стандартный набор

Определён в `modules/dashboard/user_dashboard.py` — переменная
`DEFAULT_WIDGETS`. Измените, если нужно настроить шаблон по умолчанию.

---

## Персонализация sidebar

**Настройки каждого пользователя хранятся в таблице `user_sidebar`.**

### Структура

| Поле | Тип | Описание |
|---|---|---|
| `user_id` | INTEGER PRIMARY KEY | Владелец |
| `pinned_sections` | JSONB | Массив ключей закреплённых |
| `hidden_sections` | JSONB | Массив ключей скрытых |
| `updated_at` | TIMESTAMP | Дата последнего изменения |

### Реестр разделов

Файл `modules/core/sidebar.py`. Каждый раздел:

```python
'finance': {
    'name': 'Финансы',
    'icon': 'fa-chart-line',
    'endpoint': 'dashboard.finance',
    'fixed': False,          # можно ли скрывать
    'admin_only': False,     # только для админов
    'group': None,           # 'service' или 'admin'
}
```

### Логика меню

- **Фиксированные** — всегда в основном блоке.
- **Закреплённые** — в основном блоке с жёлтой звездой.
- **Скрытые** — вообще не показываются.
- **Опциональные не закреплённые** — в блоке «Все разделы».

### API-эндпоинты

| Метод | URL | Что делает |
|---|---|---|
| POST | `/api/sidebar/pin` | Закрепить раздел |
| POST | `/api/sidebar/unpin` | Открепить |
| POST | `/api/sidebar/hide` | Скрыть |
| POST | `/api/sidebar/unhide` | Вернуть скрытый |
| POST | `/api/sidebar/reset` | Сбросить все настройки |

### Как добавить новый раздел в sidebar

1. Откройте `modules/core/sidebar.py`.
2. Добавьте запись в `SECTIONS`.
3. Укажите `fixed: True`, если раздел должен быть всегда виден.
4. Перезапустите приложение.

---

## Диагностика

### Проверка статуса

```bash
docker compose ps
```

Ожидаемый вывод:
```
report_app   Up
report_db    Up (healthy)
```

### Логи

```bash
# Логи приложения
docker compose logs -f app

# Логи БД
docker compose logs -f db

# Только последние 50 строк
docker compose logs --tail=50 app

# Файл логов приложения
tail -f ~/core_it/logs/app.log
```

### Healthcheck

```bash
curl http://localhost:5000/health
# {"status": "ok"}
```

### Проверка подключения к БД

```bash
docker compose exec db psql -U report_user -d report_db -c "SELECT count(*) FROM applications;"
```

### Проверка sidebar

```bash
docker compose exec app python3 -c "
from modules.core.sidebar import build_sidebar
menu = build_sidebar(user_id=5, is_admin=False)
for group in ['main', 'hidden', 'service', 'admin']:
    print(group, ':', [i['key'] for i in menu[group]])
"
```

### Проверка виджетов

```bash
docker compose exec app python3 -c "
from modules.dashboard.widgets import WIDGETS, render_widget
for key in WIDGETS:
    r = render_widget(key)
    status = 'OK' if r and not r.get('error') else 'FAIL'
    print(f'{key}: {status}')
"
```

---

## Nginx и SSL

### Конфигурация Nginx

Файл `/etc/nginx/sites-available/portal.stng.ru`:

```nginx
# HTTP → HTTPS
server {
    listen 80;
    server_name portal.stng.ru;
    return 301 https://$host$request_uri;
}

# HTTPS
server {
    listen 443 ssl;
    http2 on;
    server_name portal.stng.ru;

    ssl_certificate     /etc/nginx/ssl/portal-fullchain.crt;
    ssl_certificate_key /etc/nginx/ssl/portal.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 200M;
    proxy_read_timeout 900s;
    proxy_send_timeout 900s;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Проверка и перезагрузка

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## Структура базы данных

### Основные таблицы

| Таблица | Назначение | Логика обновления |
|---|---|---|
| `applications` | Заявки | Upsert по (номер, дата) |
| `registers` | Реестры | Upsert по номеру |
| `contracts` | Договоры | Upsert по external_code |
| `debts` | КЗ/ДЗ | Полная замена при импорте |
| `application_contracts` | Связи заявок и договоров | Пересобирается после импорта |
| `users` | Пользователи | Через админку |
| `saved_reports` | Сохранённые отчёты конструктора | Через UI |
| `user_dashboards` | Персональные дашборды | Через UI |
| `user_sidebar` | Настройки бокового меню | Через UI |
| `objects` | Справочник объектов | Импорт CSV или вручную |
| `object_tokens` | Токены объектов для матчинга | Пересобирается вручную |
| `object_tokens_raw` | Сырые токены (для отладки) | Устаревшая |

### Представления

| Представление | Что делает |
|---|---|
| `v_applications_full` | Заявки + присоединённые реестры |
| `v_registers` | Реестры с вычисленным статусом |
| `v_pq_quick_report` | Быстрый отчёт |

### Поля `applications` (ключевые)

| Поле | Тип | Откуда |
|---|---|---|
| `номер_заявки` | varchar | Excel |
| `дата` | date | Excel |
| `оплачена` | varchar(3) | Excel |
| `статус_согласования` | text | Excel |
| `состояние_заявки` | text | Excel |
| `период_услуги` | date | Из назначения платежа |
| `договор_код` | text | Excel |
| `документ_расчетов_с_контрагентом` | text | Excel |
| `сумма_заявки` | numeric | Excel |
| `дата_оплаты_фактич` | date | Excel |
| `object_id` | integer | Матчинг |
| `object_match_confidence` | text | Матчинг |

---

## Логика вычислений

### Определение «оплачена»

Статус берётся **напрямую из Excel**. Не вычисляется.

### Определение «период услуги»

Функция `extract_period`:

1. Сначала ищет фразу `за <месяц> <год>`.
2. Если не найдено — ищет `от ДД.ММ.ГГГГ` после «счёт».
3. Дата договора игнорируется.

### Прогноз исчерпания лимита

Для каждого договора:

```
дни с первой заявки = max(30, min(сегодня - первая_заявка, 1095))
дневной_темп = потрачено / дни
дней_до_исчерпания = остаток / дневной_темп
```

Отсечки: если дней > 20 лет — не показываем.

### Ответственный по договору

Вычисляется при пересборке связей:

1. Для каждого договора собираются все заявки.
2. Считается самый частый ответственный.
3. При равенстве — берётся тот, у кого более свежая заявка.

### ЦФО по договору

Аналогично ответственному: берётся самый частый ЦФО среди заявок договора.

### Связь заявка ↔ договор

Через поле **`договор_код`** в заявках и **`external_code`** в договорах.

### Сверка КЗ ↔ заявки

На уровне договора:

- КЗ из `debts` по `договор_код`;
- заявки через `application_contracts`;
- учитываются только заявки: `оплачена = 'Нет'`, статус согласования
  непустой, состояние не `Аннулирован`/`Подготовлен`.

Построчная сверка — по полю «Документ расчётов» с нормализацией
(удаление пробелов, времени, регистра).

---

## Частые проблемы

### Пользователь не может войти

1. Проверьте, что он есть в БД:
   ```bash
   docker compose exec db psql -U report_user -d report_db -c "SELECT email, role, is_active FROM users;"
   ```
2. Если забыл пароль — сбросьте через админку.

### Импорт падает с ошибкой

Проверьте логи:
```bash
docker compose logs --tail=50 app | grep -A5 "IMPORT ERROR"
```

Частые причины:
- нет прав на запись файла (`chmod`);
- ошибка в Excel (не тот лист, не те колонки);
- проблема с кодировкой (сохранить как UTF-8).

### Портал недоступен

1. `docker compose ps` — контейнеры работают?
2. `curl http://localhost:5000/health` — приложение отвечает?
3. `sudo nginx -t` — конфиг валиден?
4. `sudo systemctl status nginx` — Nginx запущен?

### БД «тормозит»

Найдите медленные запросы:
```bash
docker compose logs app | grep "SLOW QUERY"
```

Если много — можно добавить индексы. Покажите список — подскажу.

### После перезапуска пропали данные

Проверьте, что не выполнялся `docker compose down -v`.

### Ошибка `ModuleNotFoundError`

Значит, образ не пересобран после изменения `requirements.txt`:

```bash
docker compose down
docker compose build --no-cache app
docker compose up -d
```

### Дашборд показывает пустые виджеты

1. Откройте F12 → Console — нет ли JS-ошибок.
2. Проверьте, что Chart.js загружается — `typeof Chart` в консоли должен
   вернуть `function`.
3. Если графики пусты, а KPI и таблицы — нет, проблема в подключении
   Chart.js. Он должен быть подключён в `{% block head_extra %}`.

### Sidebar показывает не все разделы

1. Проверьте настройки пользователя:
   ```bash
   docker compose exec db psql -U report_user -d report_db -c "SELECT * FROM user_sidebar WHERE user_id = <ID>;"
   ```
2. Если там мусор — сбросьте:
   ```sql
   DELETE FROM user_sidebar WHERE user_id = <ID>;
   ```

---

*Последнее обновление: 23 сентября 2026*