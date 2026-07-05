FROM python:3.12-slim

# APP_PORT is intentionally not baked in: the server falls back to the
# platform-injected PORT (Render/Railway) and then to 8000.
ENV APP_HOST=0.0.0.0 \
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
    CMD python -c "import os, urllib.request; port = os.environ.get('APP_PORT') or os.environ.get('PORT') or '8000'; urllib.request.urlopen('http://127.0.0.1:' + port + '/readyz', timeout=3).read()"

CMD ["python", "app.py"]
