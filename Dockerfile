# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 180 --retries 10 -r requirements.txt
RUN useradd --uid 10001 --create-home app && mkdir /models && chown app /models
COPY src ./src
COPY scripts ./scripts
USER app
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
