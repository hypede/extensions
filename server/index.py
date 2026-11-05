"""Точка входа для Vercel: Vercel находит здесь ASGI-приложение «app».

Данные — в Vercel Blob (BLOB_READ_WRITE_TOKEN появляется, когда хранилище
подключено к проекту). Остальные настройки — переменные окружения, см.
hypede_store/config.py и README.md.
"""

from hypede_store.app import create_app

app = create_app()
