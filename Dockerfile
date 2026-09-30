FROM python:3.12-slim

LABEL org.opencontainers.image.title="Nobat" \
      org.opencontainers.image.description="Private, self-hosted appointment panel with Jalali calendar" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/nobat.db
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN useradd --uid 1000 --create-home nobat && mkdir -p /data && chown nobat /data
USER nobat

EXPOSE 8000
# ProxyHandler({}) ignores any HTTP_PROXY set in the environment for this local check.
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request as u; u.build_opener(u.ProxyHandler({})).open('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
