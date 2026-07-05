FROM python:3.12-slim

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin callpilot \
    && mkdir -p /app /data \
    && chown -R callpilot:callpilot /app /data

COPY --chown=callpilot:callpilot app.py worker.py ./
COPY --chown=callpilot:callpilot callpilot ./callpilot

USER callpilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('APP_PORT', '8000') + '/readyz', timeout=3).read()"

CMD ["python", "app.py"]
