#!/usr/bin/env sh
set -eu

if [ -n "${SOUL_PYTHON_BIN:-}" ]; then
  if [ -x "${SOUL_PYTHON_BIN}" ]; then
    printf '%s\n' "${SOUL_PYTHON_BIN}"
    exit 0
  fi
  echo "SOUL_PYTHON_BIN is set but not executable: ${SOUL_PYTHON_BIN}" >&2
  exit 1
fi

if [ -n "${VIRTUAL_ENV:-}" ]; then
  for candidate in "${VIRTUAL_ENV}/bin/python" "${VIRTUAL_ENV}/Scripts/python.exe"; do
    if [ -x "${candidate}" ]; then
      printf '%s\n' "${candidate}"
      exit 0
    fi
  done
fi

for candidate in ".venv/bin/python" ".venv/Scripts/python.exe"; do
  if [ -x "${candidate}" ]; then
    printf '%s\n' "${candidate}"
    exit 0
  fi
done

if command -v python >/dev/null 2>&1; then
  printf 'python\n'
  exit 0
fi

if command -v python3 >/dev/null 2>&1; then
  printf 'python3\n'
  exit 0
fi

echo "Python was not found. Install Python 3.11+ or create a local .venv." >&2
exit 127
