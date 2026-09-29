"""
Центральный конфиг приложения.
Все настройки читаются из переменных окружения с разумными умолчаниями.
"""
import os


class Config:
    # === База данных ===
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    # === Сессии ===
    SESSION_LIFETIME_HOURS = int(os.environ.get('SESSION_LIFETIME_HOURS', '8'))
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'

    # === Flask ===
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', str(200 * 1024 * 1024)))

    # === Логирование ===
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', '/app/logs/app.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', str(10 * 1024 * 1024)))   # 10 MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '5'))

    # === Мониторинг медленных запросов ===
    SLOW_QUERY_THRESHOLD = float(os.environ.get('SLOW_QUERY_THRESHOLD', '3.0'))   # сек

    # === Бизнес-константы ===
    # ИСД безреестровых заявок
    BEZREESTROVIY_ISD = {
        '0036045', '0025948', '0026977', '0034230',
        '0032259', '0031112', '0031124', '0026099',
    }