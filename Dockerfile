FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY backup.py send.py sign_in.py ui.py ./
COPY static/ ./static/
COPY settings/ ./settings/
COPY logger/ ./logger/

RUN mkdir -p /data/sessions
WORKDIR /data

EXPOSE 8080
CMD ["python", "/app/ui.py"]
