.PHONY: help test smoke smoke-auto wake wake-echo wake-repeat lint fmt validate check clean

UV := $(shell command -v uv 2>/dev/null)

# An activated virtualenv in the developer's shell is not this project's
# environment; unset it so uv manages .venv without warning on every run.
unexport VIRTUAL_ENV

help:
	@echo "make test        run the offline suite (no model calls)"
	@echo "make smoke       run the packaged smoke test against a real Claude session"
	@echo "make smoke-auto  the same, skipping the one interactive check"
	@echo "make wake        verify the asynchronous wake automatically, on a pty"
	@echo "make wake-echo   drive the pty harness against a fake terminal (no model)"
	@echo "make wake-repeat run the wake check ten times to measure its stability"
	@echo ""
	@echo "Debugging the wake harness:"
	@echo "  WAKE_TRACE=0   silence the step-by-step trace (on by default)"
	@echo "  WAKE_BUDGET=n  override the per-check budget, in seconds"
	@echo "  the raw terminal stream of each run is left in tmp/smoke/<test>/"
	@echo "make lint        run ruff"
	@echo "make fmt         apply ruff formatting fixes"
	@echo "make validate    validate the plugin manifest with the Claude CLI"
	@echo "make check       test + lint + validate"

ifeq ($(UV),)
test smoke smoke-auto wake wake-echo wake-repeat lint fmt:
	@echo "uv is required for development tooling."
	@echo "Install it with 'brew install uv' or from https://docs.astral.sh/uv/."
	@echo "The plugin itself needs no dependencies; this is only for tests."
	@exit 1
else
test:
	uv run --group dev pytest -q -m "not smoke and not pty"

# Spends real model usage, so it is never part of `make test` or `make check`.
# -s keeps stdin and stdout attached for the one interactive check. -rs lists why
# anything skipped: a check that could not reach the model observed nothing, and
# that has to be readable at the end of the run rather than inferred. The scratch
# workspace is left under tmp/smoke/ afterwards so a failure can be inspected.
smoke:
	uv run --group dev pytest -m smoke -s -v -rs

smoke-auto:
	SMOKE_SKIP_INTERACTIVE=1 uv run --group dev pytest -m smoke -s -v -rs

# Spec-0002. Automates the one smoke check a person otherwise confirms, by
# driving a real interactive session on a pseudo-terminal. Opt-in on purpose:
# it spends model usage on two real reviews, and it is the component here most
# exposed to changes in the terminal interface, so it never gates anything.
wake:
	uv run --group dev pytest -m pty -s -v -rs

# The same harness against a fake terminal that only echoes what it captured, so
# a stalled live run can be attributed: if this passes, input is being delivered
# and turn boundaries are being detected, and the stall is in the session under
# test. No model, no cost — these also run inside `make test`.
wake-echo:
	uv run --group dev pytest -m echo -s -v -rs

# Acceptance criterion 1: reliable across ten consecutive runs. Stops at the
# first failure, since that is the answer.
wake-repeat:
	@for run in 1 2 3 4 5 6 7 8 9 10; do \
	  echo "=== wake run $$run/10 ==="; \
	  uv run --group dev pytest -m pty -q -rs || exit 1; \
	done
	@echo "=== ten consecutive wake runs, no failures ==="

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
