SHELL := /bin/sh

.PHONY: build up down logs shell test docker-test lint

build:
	docker compose build app worker beat test

up:
	docker compose up -d app worker beat postgres redis chroma

down:
	docker compose down -v

logs:
	docker compose logs -f app worker beat postgres redis chroma

shell:
	docker compose run --rm app

test:
	pytest -q

docker-test:
	docker compose build app test
	docker compose up -d redis chroma postgres
	docker compose run --rm test

lint:
	python -m compileall soul scripts
