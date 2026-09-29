"""
Настройка логирования: stdout + файл с ротацией.
Вызывается один раз при старте приложения.
"""
import logging
import logging.handlers
import os

from config import Config


def setup_logging():
    """Настраивает корневой логгер."""
    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    handlers = []

    # 1. stdout — всегда
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)
    handlers.append(stdout_handler)

    # 2. Файл с ротацией — если можем
    log_dir = os.path.dirname(Config.LOG_FILE)
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            pass

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
            encoding='utf-8',
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)
    except Exception:
        # Если не удалось — работаем только со stdout
        pass

    logging.basicConfig(level=level, handlers=handlers, force=True)

    # Приглушаем шум
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)