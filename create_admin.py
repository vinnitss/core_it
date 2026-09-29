"""
Создание первого администратора.
Использование:
    python3 create_admin.py admin@stng.ru Пароль123!
"""
import sys
from sqlalchemy import text
from modules.core.utils import engine
from modules.auth.services import create_user


def main():
    email = sys.argv[1] if len(sys.argv) > 1 else 'admin@stng.ru'
    password = sys.argv[2] if len(sys.argv) > 2 else 'ChangeMe123!'

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT 1 FROM users WHERE LOWER(email) = LOWER(:e)"),
            {"e": email}
        ).fetchone()
        if existing:
            print(f"❌ Пользователь {email} уже существует")
            sys.exit(1)

    create_user(
        email=email,
        password=password,
        role='admin',
        department=None,
        can_import=True,
        must_change_password=True,
    )
    print(f"✅ Создан администратор: {email}")
    print(f"   Пароль: {password}")
    print(f"   При первом входе потребуется сменить пароль.")


if __name__ == '__main__':
    main()