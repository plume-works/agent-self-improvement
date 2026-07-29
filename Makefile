.PHONY: help test lint fmt validate check clean

UV := $(shell command -v uv 2>/dev/null)

# An activated virtualenv in the developer's shell is not this project's
# environment; unset it so uv manages .venv without warning on every run.
unexport VIRTUAL_ENV

help:
	@echo "make test      run the test suite"
	@echo "make lint      run ruff"
	@echo "make fmt       apply ruff formatting fixes"
	@echo "make validate  validate the plugin manifest with the Claude CLI"
	@echo "make check     test + lint + validate"

ifeq ($(UV),)
test lint fmt:
	@echo "uv is required for development tooling."
	@echo "Install it with 'brew install uv' or from https://docs.astral.sh/uv/."
	@echo "The plugin itself needs no dependencies; this is only for tests."
	@exit 1
else
test:
	uv run --group dev pytest -q

lint:
	uv run --group dev ruff check plugin tests

fmt:
	uv run --group dev ruff check --fix plugin tests
endif

validate:
	@command -v claude >/dev/null 2>&1 || { \
	  echo "claude CLI not found; skipping manifest validation"; exit 0; }
	claude plugin validate ./plugin

check: test lint validate

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
