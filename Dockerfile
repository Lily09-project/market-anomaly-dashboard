FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements-runtime.lock ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock

COPY --chown=appuser:appuser . .
RUN python run_all.py --mode sample && chown -R appuser:appuser /app

USER appuser
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/_stcore/health', timeout=3).read()"]

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8765", "--server.headless=true", "--server.fileWatcherType=none", "--browser.gatherUsageStats=false"]
