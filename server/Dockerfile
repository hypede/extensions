# API каталога extensions.hypede.xyz с антивирусом ClamAV.
#   docker build -t hypede-store server/
#   docker run -d -p 127.0.0.1:8080:8080 -v hypede-store:/data \
#     -e HYPEDE_STORE_MODERATORS=ваш_ник hypede-store
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends clamav clamav-daemon \
 && rm -rf /var/lib/apt/lists/* \
 && sed -i 's/^Example/#Example/' /etc/clamav/freshclam.conf || true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hypede_store ./hypede_store
COPY docker-start.sh .

ENV HYPEDE_STORE_DATA=/data \
    HYPEDE_STORE_PUBLIC_URL=https://api.extensions.hypede.xyz \
    HYPEDE_STORE_ORIGINS=https://extensions.hypede.xyz
VOLUME /data
EXPOSE 8080
# Сервис работает не от root.
RUN useradd --system --home /app store && mkdir -p /data && chown store /data /var/lib/clamav
USER store
CMD ["./docker-start.sh"]
