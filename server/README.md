# Сервис каталога extensions.hypede.xyz

Аккаунты, публикация расширений GNOME Shell и тем HypeDE, проверка и
модерация. Сам сайт — статичные страницы в корне репозитория (`catalog/`,
`ru/catalog/`, `assets/store.js`), их раздаёт GitHub Pages; этот сервис —
API, к которому сайт ходит по адресу из `assets/config.js`
(`https://api.extensions.hypede.xyz`).

## Что умеет

- **Аккаунт**: почта и пароль (scrypt), ник, имя, фото (пересобирается в
  PNG 256×256 — метаданные и всё лишнее из файла пропадают), описание до
  500 символов. Вход — подписанный токен в заголовке `Authorization`
  (сайт и API на разных доменах, куки между ними браузеры блокируют);
  «Выйти» и смена пароля отзывают все выданные токены.
- **Публикация**: расширение — ZIP как от `gnome-extensions pack`
  (`metadata.json` и `extension.js` в корне, GNOME Shell 48–51); тема —
  JSON-файл темы HypeDE. Автор подтверждает, что имеет право публиковать
  файл. Новая версия ждёт проверки, а прошлая одобренная остаётся доступной.
- **Автоматическая проверка** (`hypede_store/checks.py`): ClamAV (на
  своём сервере — сразу, на Vercel — из GitHub Actions, см. ниже); разбор
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

## Где хранятся данные

`hypede_store/storage.py`: если задан `BLOB_READ_WRITE_TOKEN` — в приватном
хранилище Vercel Blob, иначе на диске в `HYPEDE_STORE_DATA`. Аккаунты,
работы и индексы — документы JSON (`hypede_store/repo.py`), каталог
читается одним документом и кэшируется на CDN, поэтому обращений к
хранилищу мало.

## Vercel

1. Проект с корнем `server/` (Root Directory), фреймворк FastAPI —
   `index.py` отдаёт приложение.
2. Storage → Create → Blob, доступ **Private**, подключить к проекту —
   появится `BLOB_READ_WRITE_TOKEN`.
3. Переменные окружения:

   | Переменная | Значение |
   |---|---|
   | `HYPEDE_STORE_SECRET` | длинная случайная строка (подпись входов) |
   | `HYPEDE_STORE_MODERATORS` | ваш ник или почта |
   | `HYPEDE_STORE_PUBLIC_URL` | адрес API, например `https://api.extensions.hypede.xyz` |
   | `HYPEDE_STORE_ORIGINS` | `https://extensions.hypede.xyz` |
   | `HYPEDE_STORE_SCAN_TOKEN` | ещё одна случайная строка — для антивируса |

4. Домен `api.extensions.hypede.xyz`: Settings → Domains, у регистратора —
   запись CNAME `api.extensions` → `cname.vercel-dns.com`. Адрес API для
   сайта — в `assets/config.js`.
5. Антивирус: в репозитории сайта секрет `HYPEDE_SCAN_TOKEN` с тем же
   значением, что `HYPEDE_STORE_SCAN_TOKEN`. Workflow
   `.github/workflows/antivirus.yml` каждые полчаса сканирует новые
   загрузки ClamAV; заражённые отклоняются сами.

Ограничение Vercel: запрос и ответ функции — до 4,5 МБ, поэтому файлы
расширений, тем и картинки — до 4 МБ.

## Свой сервер

```
pip install -r server/requirements.txt
cd server
HYPEDE_STORE_PUBLIC_URL=http://127.0.0.1:8080 HYPEDE_STORE_ORIGINS=http://127.0.0.1:8000 \
HYPEDE_STORE_MODERATORS=ваш_ник HYPEDE_STORE_SECRET=что-нибудь-длинное \
python -m uvicorn index:app --port 8080
```

Сайт рядом: `python3 -m http.server 8000` в корне репозитория, а в консоли
браузера — `localStorage.hypedeApi = 'http://127.0.0.1:8080'`.

Docker-образ с ClamAV — `server/Dockerfile`, за Caddy
(`server/Caddyfile.example`). Данные — в томе `/data`.

Модераторов можно назначать и командой
`python -m hypede_store.admin moderator НИК` (там же `ban`, `unban`,
`queue`); она работает с тем же хранилищем, что и сервис.

## Тесты

```
cd server && python -m pytest tests
```
