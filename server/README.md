# Сервис каталога extensions.hypede.xyz

Аккаунты, публикация расширений GNOME Shell и тем HypeDE, проверка и
модерация. Сам сайт — статичные страницы в корне репозитория (`catalog/`,
`ru/catalog/`, `assets/store.js`), их раздаёт GitHub Pages; этот сервис —
API, к которому сайт ходит по адресу из `assets/config.js`
(`https://api.extensions.hypede.xyz`).

## Что умеет

- **Аккаунт**: почта и пароль (scrypt), ник, имя, фото (пересобирается в
  PNG 256×256 — метаданные и всё лишнее из файла пропадают), описание до
  500 символов. Сессия — куки `HttpOnly`, `Secure`, `SameSite=Lax`.
- **Публикация**: расширение — ZIP как от `gnome-extensions pack`
  (`metadata.json` и `extension.js` в корне, GNOME Shell 48–51); тема —
  JSON-файл темы HypeDE. Автор подтверждает, что имеет право публиковать
  файл. Новая версия ждёт проверки, а прошлая одобренная остаётся доступной.
- **Автоматическая проверка** (`hypede_store/checks.py`): ClamAV; разбор
  архива (выход за пределы архива, символьные ссылки, слишком много файлов,
  исполняемые файлы и библиотеки — отклоняются сразу); места кода, которые
  стоит посмотреть: запуск программ, `sudo`/`pkexec`, сеть, `eval`, запись
  в системные каталоги, обращение к паролям и ключам, сжатый или запутанный
  код. У тем — только известные ключи формата, без сетевых адресов,
  встроенные картинки и видео проверяются по сигнатуре, SVG — без скриптов
  и внешних ссылок.
- **Ручная проверка**: ничего не публикуется без модератора. На странице
  `#/moderate` модератор видит отчёт, скачивает версию, одобряет или
  отклоняет с пояснением автору. Блокировка автора —
  `POST /api/mod/users/{ник}/ban`.
- **Отказ от ответственности** — на каждой странице каталога, у кнопки
  «Скачать» и в форме публикации: HypeDE не несёт ответственности за вашу
  систему.

## Запуск

```
pip install -r server/requirements.txt
cd server
HYPEDE_STORE_SECURE=0 HYPEDE_STORE_PUBLIC_URL=http://127.0.0.1:8080 \
HYPEDE_STORE_ORIGINS=http://127.0.0.1:8000 HYPEDE_STORE_MODERATORS=ваш_ник \
python -m uvicorn --factory hypede_store.app:create_app --port 8080
```

Сайт рядом: `python3 -m http.server 8000` в корне репозитория, а в консоли
браузера — `localStorage.hypedeApi = 'http://127.0.0.1:8080'`.

В бою — Docker-образ с ClamAV (`server/Dockerfile`) за Caddy
(`server/Caddyfile.example`) на `api.extensions.hypede.xyz`. Данные — в
томе `/data`: база SQLite, файлы версий, картинки. Резервная копия — этот
каталог целиком.

| Переменная | Что это |
|---|---|
| `HYPEDE_STORE_DATA` | каталог данных |
| `HYPEDE_STORE_ORIGINS` | адреса сайта через запятую (CORS) |
| `HYPEDE_STORE_MODERATORS` | ники или почта модераторов через запятую |
| `HYPEDE_STORE_PUBLIC_URL` | внешний адрес API, для ссылок на файлы |
| `HYPEDE_STORE_SECURE` | `0` — куки и по HTTP (только для проверки) |
| `HYPEDE_STORE_CLAMAV` | путь к `clamdscan`/`clamscan`, если не в `PATH` |

Модераторов можно назначать и командой:
`python -m hypede_store.admin moderator НИК` (там же `ban`, `unban`,
`queue`).

## Тесты

```
cd server && python -m pytest tests
```
