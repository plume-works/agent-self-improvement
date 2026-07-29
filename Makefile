.PHONY: help test smoke smoke-auto lint fmt validate check clean

UV := $(shell command -v uv 2>/dev/null)

# An activated virtualenv in the developer's shell is not this project's
# environment; unset it so uv manages .venv without warning on every run.
unexport VIRTUAL_ENV

help:
	@echo "make test        run the offline suite (no model calls)"
	@echo "make smoke       run the packaged smoke test against a real Claude session"
	@echo "make smoke-auto  the same, skipping the one interactive check"
	@echo "make lint        run ruff"
	@echo "make fmt         apply ruff formatting fixes"
	@echo "make validate    validate the plugin manifest with the Claude CLI"
	@echo "make check       test + lint + validate"

ifeq ($(UV),)
test smoke smoke-auto lint fmt:
	@echo "uv is required for development tooling."
	@echo "Install it with 'brew install uv' or from https://docs.astral.sh/uv/."
	@echo "The plugin itself needs no dependencies; this is only for tests."
	@exit 1
else
test:
	uv run --group dev pytest -q -m "not smoke"

# Spends real model usage, so it is never part of `make test` or `make check`.
# -s keeps stdin and stdout attached for the one interactive check. The scratch
# workspace is left under tmp/smoke/ afterwards so a failure can be inspected.
smoke:
	uv run --group dev pytest -m smoke -s -v

smoke-auto:
	SMOKE_SKIP_INTERACTIVE=1 uv run --group dev pytest -m smoke -s -v

lint:
	uv run --group dev ruff check plugin tests

fmt:
	uv run --group dev ruff check --fix plugin tests
endif

# Validation needs a CLI new enough to know every hook event the plugin
# registers. An older one reports "Invalid key in record" for events it has
# never heard of, which is a toolchain gap rather than a manifest error.
validate:
	@command -v claude >/dev/null 2>&1 || { \
	  echo "claude CLI not found; skipping manifest validation"; exit 0; }
	@claude plugin validate ./plugin || { \
	  echo ""; \
	  echo "Installed Claude Code: $$(claude --version)"; \
	  echo "This plugin targets 2.1.196 or later. If the failure names a hook"; \
	  echo "event as an invalid key, the CLI predates that event."; \
	  echo "Upgrade with: npm install -g @anthropic-ai/claude-code"; \
	  exit 1; }

check: test lint validate

clean:
	rm -rf .pytest_cache .ruff_cache tmp/smoke
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
