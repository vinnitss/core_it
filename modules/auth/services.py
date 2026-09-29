"""
Сервисы аутентификации: пользователь, пароли, Flask-Login User.
"""
from datetime import datetime

import bcrypt
from flask_login import UserMixin
from sqlalchemy import text

from modules.core.utils import engine


# ==================== КЛАСС ПОЛЬЗОВАТЕЛЯ ====================
class User(UserMixin):
    """Класс для Flask-Login. Поле 'department' соответствует БД-столбцу 'цфо'."""

    def __init__(self, id, email, role, department,
                 can_import, must_change_password, is_active_flag=True,
                 start_page='home', can_edit_approvers=False):
        self.id = id
        self.email = email
        self.role = role
        self.department = department
        self.can_import = can_import
        self.must_change_password = must_change_password
        self._is_active = is_active_flag
        self.start_page = start_page
        self.can_edit_approvers = can_edit_approvers

    @property
    def is_active(self):
        return self._is_active

    @property
    def is_admin(self):
        return self.role == 'admin'


# ==================== ПАРОЛИ ====================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


# ==================== CRUD ====================
def _row_to_user(row):
    if row is None:
        return None
    return User(
        id=row.id,
        email=row.email,
        role=row.role,
        department=row.цфо,
        can_import=row.can_import,
        must_change_password=row.must_change_password,
        is_active_flag=row.is_active,
        start_page=getattr(row, 'start_page', 'home') or 'home',
        can_edit_approvers=getattr(row, 'can_edit_approvers', False) or False,
    )


def get_user_by_id(user_id):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, email, role, цфо, can_import, must_change_password, is_active, start_page, can_edit_approvers
            FROM users WHERE id = :id
        """), {"id": user_id}).fetchone()
    return _row_to_user(row)


def get_user_by_email(email):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, email, role, цфо, can_import, must_change_password, is_active, start_page, can_edit_approvers
            FROM users WHERE LOWER(email) = LOWER(:e)
        """), {"e": email}).fetchone()
    return _row_to_user(row)


def authenticate(email, password):
    """Возвращает User при успешной проверке пароля, иначе None."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, email, password_hash, role, цфо, can_import,
                   must_change_password, is_active, start_page, can_edit_approvers
            FROM users WHERE LOWER(email) = LOWER(:e)
        """), {"e": email}).fetchone()

    if not row:
        return None
    if not row.is_active:
        return None
    if not verify_password(password, row.password_hash):
        return None

    # Обновляем last_login
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET last_login = NOW() WHERE id = :id"),
            {"id": row.id}
        )
        conn.commit()

    return User(
        id=row.id,
        email=row.email,
        role=row.role,
        department=row.цфо,
        can_import=row.can_import,
        must_change_password=row.must_change_password,
        is_active_flag=row.is_active,
        start_page=getattr(row, 'start_page', 'home') or 'home',   # ← фикс: передаём start_page
        can_edit_approvers=getattr(row, 'can_edit_approvers', False) or False,
    )


def create_user(email, password, role='viewer', department=None,
                can_import=False, must_change_password=True, can_edit_approvers=False):
    """Создаёт пользователя. Если email занят — бросает ValueError."""
    email = email.strip().lower()
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT 1 FROM users WHERE LOWER(email) = LOWER(:e)"),
            {"e": email}
        ).fetchone()
        if existing:
            raise ValueError(f"Email {email} уже занят")

        conn.execute(text("""
            INSERT INTO users (email, password_hash, role, цфо, can_import, must_change_password, can_edit_approvers)
            VALUES (:e, :p, :r, :d, :ci, :mcp, :cea)
        """), {                                                      # ↑ фикс: добавлен :cea
            "e": email,
            "p": hash_password(password),
            "r": role,
            "d": department,
            "ci": can_import,
            "mcp": must_change_password,
            "cea": can_edit_approvers,
        })
        conn.commit()
    return get_user_by_email(email)


def set_password(user_id, new_password):
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET password_hash = :p WHERE id = :id"),
            {"p": hash_password(new_password), "id": user_id}
        )
        conn.commit()


def set_must_change_password(user_id, value: bool):
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET must_change_password = :v WHERE id = :id"),
            {"v": value, "id": user_id}
        )
        conn.commit()


def list_users():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, email, role, цфо, can_import, must_change_password,
                   is_active, created_at, last_login
            FROM users ORDER BY id
        """)).fetchall()
    return [dict(r._mapping) for r in rows]


def update_user(user_id, role=None, department=None,
                can_import=None, is_active=None, can_edit_approvers=None):
    """Частичное обновление. Поля, где None — не меняются."""
    sets = []
    params = {"id": user_id}
    if role is not None:
        sets.append("role = :role")
        params["role"] = role
    if department is not None:
        sets.append("цфо = :dep")
        params["dep"] = department
    if can_import is not None:
        sets.append("can_import = :ci")
        params["ci"] = can_import
    if is_active is not None:
        sets.append("is_active = :ia")
        params["ia"] = is_active
    if can_edit_approvers is not None:
        sets.append("can_edit_approvers = :cea")
        params["cea"] = can_edit_approvers
    if not sets:
        return
    with engine.connect() as conn:
        conn.execute(
            text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"),
            params
        )
        conn.commit()


def verify_password_by_id(user_id, password):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash FROM users WHERE id = :id"),
            {"id": user_id}
        ).fetchone()
    if not row:
        return False
    return verify_password(password, row.password_hash)


def set_start_page(user_id, start_page):
    """Устанавливает стартовую страницу: 'home' или 'my_dashboard'."""
    if start_page not in ('home', 'my_dashboard'):
        return
    with engine.connect() as conn:
        conn.execute(text(
            "UPDATE users SET start_page = :sp WHERE id = :id"
        ), {'sp': start_page, 'id': user_id})
        conn.commit()