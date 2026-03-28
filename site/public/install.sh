#!/usr/bin/env sh
set -eu

REPO_OWNER="sparkz-technology"
REPO_NAME="soul"
RELEASE_API_URL="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
MAIN_ARCHIVE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/main.tar.gz"

if [ -n "${SOUL_PYTHON:-}" ]; then
  PYTHON_BIN="$SOUL_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  printf '%s\n' "SOUL installer needs Python 3.11 or newer." >&2
  exit 127
fi

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("SOUL needs Python 3.11 or newer.")
PY

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  printf 'pip is required but was not found for %s.\n' "$PYTHON_BIN" >&2
  exit 127
fi

release_tag=$(
  "$PYTHON_BIN" - "$RELEASE_API_URL" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = json.load(response)
except Exception:
    print("", end="")
    raise SystemExit(0)

print(payload.get("tag_name", ""), end="")
PY
)

if [ -n "$release_tag" ]; then
  package_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/tags/${release_tag}.tar.gz"
  printf 'Installing SOUL %s\n' "$release_tag"
else
  package_url="$MAIN_ARCHIVE_URL"
  printf '%s\n' "Installing SOUL from the latest main branch snapshot."
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
  "$PYTHON_BIN" -m pip install --upgrade --user "$package_url"
  user_bin_dir=$(
    "$PYTHON_BIN" - <<'PY'
import site

print(site.USER_BASE + "/bin")
PY
  )
else
  "$PYTHON_BIN" -m pip install --upgrade "$package_url"
  user_bin_dir=""
fi

printf '\n%s\n' "SOUL is installed."
if [ -n "$user_bin_dir" ]; then
  printf 'Make sure %s is on your PATH.\n' "$user_bin_dir"
fi
printf '%s\n' "Next steps:"
printf '  %s\n' "soul version"
printf '  %s\n' "soul db init"
printf '  %s\n' "soul chat"
