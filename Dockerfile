FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc curl ffmpeg libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt README.md ./
COPY soul ./soul
COPY soul_data ./soul_data
COPY scripts ./scripts

RUN pip install --upgrade pip setuptools wheel \
    && pip install -e .[all] \
    && pip install pytest

ENTRYPOINT ["python", "-m", "soul.cli"]
