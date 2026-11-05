#!/bin/sh
# Базы ClamAV: скачать при старте и обновлять раз в 6 часов. Пока базы нет,
# загрузки просто ждут ручной проверки («антивирус не запускался»).
set -e
( while true; do freshclam --quiet --datadir=/var/lib/clamav || true; sleep 21600; done ) &
exec python -m uvicorn --factory hypede_store.app:create_app --host 0.0.0.0 --port 8080 \
    --proxy-headers --forwarded-allow-ips='*'
