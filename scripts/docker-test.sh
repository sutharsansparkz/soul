#!/bin/sh
set -eu

docker compose build app test
docker compose up -d redis chroma postgres
docker compose run --rm test
