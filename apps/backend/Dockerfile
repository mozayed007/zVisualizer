FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/backend/pyproject.toml /app/apps/backend/pyproject.toml
COPY apps/backend/app /app/apps/backend/app
COPY config /app/config
COPY docs /app/docs
COPY skills /app/skills

RUN pip install --upgrade pip setuptools wheel \
    && pip install -e /app/apps/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/apps/backend", "--host", "0.0.0.0", "--port", "8000"]
