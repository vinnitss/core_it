"""
Модуль справки.
Читает markdown-файлы из /app/docs и рендерит их в портале.
"""
import os
import re

import markdown
from markdown.extensions.toc import slugify
from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

help_bp = Blueprint('help', __name__, template_folder='../../templates/help')

DOCS_DIR = '/app/docs'

DOCS = {
    'readme': {
        'file': 'README.md',
        'title': 'Обзор системы',
        'icon': 'fa-book',
        'admin_only': False,
    },
    'user': {
        'file': 'user-guide.md',
        'title': 'Руководство пользователя',
        'icon': 'fa-user',
        'admin_only': False,
    },
    'admin': {
        'file': 'admin-guide.md',
        'title': 'Руководство администратора',
        'icon': 'fa-user-shield',
        'admin_only': True,
    },
}


def _custom_slugify(value, separator):
    """
    Slugify с поддержкой кириллицы.
    Например: «Вход в систему» → «вход-в-систему».
    """
    value = str(value).strip().lower()
    # Убираем всё, кроме букв (включая кириллицу), цифр, пробелов и дефисов
    value = re.sub(r'[^\w\s\-]', '', value, flags=re.UNICODE)
    # Заменяем пробелы и дефисы на разделитель
    value = re.sub(r'[\s\-]+', separator, value)
    return value or 'section'


def _read_md(slug):
    """Читает markdown-файл по slug. Возвращает HTML или None."""
    if slug not in DOCS:
        abort(404)
    meta = DOCS[slug]

    if meta['admin_only'] and not (current_user.is_authenticated and current_user.is_admin):
        abort(403)

    path = os.path.join(DOCS_DIR, meta['file'])
    if not os.path.exists(path):
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        return f"<div class='alert alert-danger'>Ошибка чтения файла: {e}</div>"

    md = markdown.Markdown(
        extensions=['fenced_code', 'tables', 'toc', 'sane_lists', 'attr_list'],
        extension_configs={
            'toc': {
                'slugify': _custom_slugify,
                'permalink': False,
                'anchorlink': False,
            }
        }
    )
    return md.convert(text)


@help_bp.route('/')
@help_bp.route('/<slug>')
@login_required
def index(slug='readme'):
    html = _read_md(slug)
    if html is None:
        html = ("<div class='alert alert-warning'>"
                "<i class='fas fa-exclamation-triangle me-2'></i>"
                "Документация не найдена. Убедитесь, что файл существует в папке <code>docs/</code>."
                "</div>")
    return render_template('help/index.html',
                           docs=DOCS,
                           current_slug=slug,
                           content=html)