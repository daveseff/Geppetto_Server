FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GEPPETTO_SERVER_BASE=/var/lib/geppetto_server \
    GEPPETTO_SERVER_LOG_FILE=/dev/stdout \
    GEPPETTO_SERVER_HOST=0.0.0.0 \
    GEPPETTO_SERVER_PORT=8443

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 geppetto \
    && useradd --uid 10001 --gid 10001 --home-dir /app --create-home --shell /usr/sbin/nologin geppetto \
    && mkdir -p /app /var/lib/geppetto_server/config /var/lib/geppetto_server/pki /var/lib/geppetto_server/csr_pending /var/lib/geppetto_server/certs \
    && chown -R geppetto:geppetto /app /var/lib/geppetto_server

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /usr/local/share/geppetto_server/scripts
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER 10001:10001

EXPOSE 8443
VOLUME ["/var/lib/geppetto_server"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import ssl,urllib.request; urllib.request.urlopen('https://127.0.0.1:8443/health', context=ssl._create_unverified_context(), timeout=3).read()"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["geppetto-config-server", "serve"]
