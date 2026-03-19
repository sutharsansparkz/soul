SHELL := /bin/sh

.PHONY: build up down logs shell test docker-test lint

build:
	docker compose build app worker beat test

up:
	docker compose up -d app worker beat redis

down:
	docker compose down -v

logs:
	docker compose logs -f app worker beat redis

shell:
	docker compose run --rm app

test:
	@PYTHON_BIN=""; \
	if command -v python >/dev/null 2>&1; then \
		PYTHON_BIN=python; \
	elif command -v python3 >/dev/null 2>&1; then \
		PYTHON_BIN=python3; \
	else \
		echo "test requires Python, but neither 'python' nor 'python3' was found on PATH." >&2; \
		exit 127; \
	fi; \
	if ! $$PYTHON_BIN -c "import pytest" >/dev/null 2>&1; then \
		echo "test requires pytest for $$PYTHON_BIN, but it is not installed. Install dev dependencies from pyproject, for example: pip install -e '.[dev]'" >&2; \
		exit 1; \
	fi; \
	$$PYTHON_BIN -m pytest -q

docker-test:
	sh ./scripts/docker-test.sh

lint:
	@PYTHON_BIN=""; \
	if command -v python >/dev/null 2>&1; then \
		PYTHON_BIN=python; \
	elif command -v python3 >/dev/null 2>&1; then \
		PYTHON_BIN=python3; \
	else \
		echo "lint requires Python, but neither 'python' nor 'python3' was found on PATH." >&2; \
		exit 127; \
	fi; \
	mkdir -p .pycache; \
	PYTHONPYCACHEPREFIX=.pycache $$PYTHON_BIN -m compileall soul scripts
