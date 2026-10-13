FROM ghcr.io/astral-sh/uv:0.13.0 AS uv
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY certs ./certs

RUN uv sync --frozen --no-dev --no-editable \
    && useradd --uid 10001 --create-home atlaspipe
USER atlaspipe

EXPOSE 8000

CMD ["uvicorn", "atlaspipe.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
