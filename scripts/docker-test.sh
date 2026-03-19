#!/bin/sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
	echo "docker-test requires the Docker CLI, but 'docker' was not found on PATH. Install Docker Desktop or Docker Engine and ensure the 'docker' command is available." >&2
	exit 127
fi

docker compose build app test
docker compose up -d redis
docker compose run --rm test
