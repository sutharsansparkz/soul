SHELL := sh
PYTHON_RESOLVER := ./scripts/resolve-python.sh

# Makefile command references:
#   make test  - Run test suite with pytest (requires Python >= 3.11)
#   make lint  - Run syntax check via compileall (requires Python >= 3.11)

.PHONY: test lint


test:
	@PYTHON_BIN=`$(SHELL) $(PYTHON_RESOLVER)`; \
	PYTHON_VERSION=`$$PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'`; \
	if ! $$PYTHON_BIN -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then \
		echo "test requires Python >= 3.11, but $$PYTHON_VERSION is installed." >&2; \
		exit 1; \
	fi; \
	if ! $$PYTHON_BIN -c "import pytest" >/dev/null 2>&1; then \
		echo "test requires pytest for $$PYTHON_BIN, but it is not installed. Install dev dependencies from pyproject, for example: pip install -e '.[dev]'" >&2; \
		exit 1; \
	fi; \
	$$PYTHON_BIN -m pytest -q



lint:
	@PYTHON_BIN=`$(SHELL) $(PYTHON_RESOLVER)`; \
	PYTHON_VERSION=`$$PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'`; \
	if ! $$PYTHON_BIN -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then \
		echo "lint requires Python >= 3.11, but $$PYTHON_VERSION is installed." >&2; \
		exit 1; \
	fi; \
	mkdir -p .pycache; \
	PYTHONPYCACHEPREFIX=.pycache $$PYTHON_BIN -m compileall soul

# run
# - Starts the application in interactive mode via SOUL CLI entrypoint
# - Optionally supports `VOICE=1` or `VOICE=true` for `soul chat --voice`

.PHONY: run
run:
	@PYTHON_BIN=`$(SHELL) $(PYTHON_RESOLVER)`; \
	PYTHON_VERSION=`$$PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'`; \
	if ! $$PYTHON_BIN -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then \
		echo "run requires Python >= 3.11, but $$PYTHON_VERSION is installed." >&2; \
		exit 1; \
	fi; \
	if ! $$PYTHON_BIN -m soul --help >/dev/null 2>&1; then \
		echo "run requires the 'soul' CLI entrypoint to be installed. Use pip install -e '[dev]'" >&2; \
		exit 1; \
	fi; \
	if [ "$(VOICE)" = "1" ] || [ "$(VOICE)" = "true" ]; then \
		$$PYTHON_BIN -m soul chat --voice; \
	else \
		$$PYTHON_BIN -m soul chat; \
	fi
