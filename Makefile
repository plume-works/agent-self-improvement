.PHONY: help test smoke smoke-auto wake wake-memory wake-repeat test-harness lint fmt validate check clean clean-claude

UV := $(shell command -v uv 2>/dev/null)

# The model the smoke and wake *driving* sessions run on. The reviewer under
# test is a separate dial and stays on SELF_IMPROVE_REVIEW_MODEL. `?=` leaves an
# exported shell value in charge, and `make wake SMOKE_MODEL=` restores the
# CLI's own default.
SMOKE_MODEL ?= sonnet
SMOKE_EFFORT ?= low
export SMOKE_MODEL SMOKE_EFFORT

# No default here: the suite's own is off, and duplicating it would give two
# places to change. This only forwards an override the caller supplied.
export SMOKE_AUTO_MEMORY

# An activated virtualenv in the developer's shell is not this project's
# environment; unset it so uv manages .venv without warning on every run.
unexport VIRTUAL_ENV

# Which target a run's output belongs to. Every live run gets its own directory
# under test-runs/, named `<label>_<timestamp to the nanosecond>`, so no two runs
# can write to the same place — `make wake` cannot land in a `make smoke`
# directory, and the ten runs of `make wake-repeat` are ten readable results
# rather than one. Set per target below; a bare `pytest` run labels itself.
export TEST_RUN_LABEL

help:
	@echo "make test        run the offline suite (no model calls)"
	@echo "make smoke       run the packaged smoke test against a real Claude session"
	@echo "make smoke-auto  the same, skipping the one interactive check"
	@echo "make wake        verify the asynchronous wake automatically, on a pty"
	@echo "make wake-memory verify how the wake interacts with Claude's own auto memory"
	@echo "make wake-repeat run the wake check ten times to measure its stability"
	@echo ""
	@echo "make test-harness  self-check the pty harness against a fake terminal."
	@echo "                   Costs nothing and already runs inside 'make test';"
	@echo "                   this target reruns it alone, with the trace on."
	@echo ""
	@echo "What the smoke and wake driving sessions cost to run:"
	@echo "  SMOKE_MODEL=m  default sonnet; empty restores the CLI default"
	@echo "  SMOKE_EFFORT=l default low; empty restores the CLI default (high)"
	@echo "  SMOKE_AUTO_MEMORY=1 leave Claude's own auto memory on (default off:"
	@echo "                   it records the lesson first, so the reviewer defers)"
	@echo "  the reviewer under test has its own dials, unaffected by these:"
	@echo "  SELF_IMPROVE_REVIEW_MODEL (sonnet), SELF_IMPROVE_REVIEW_EFFORT (medium)"
	@echo ""
	@echo "Debugging the wake harness:"
	@echo "  WAKE_TRACE=0   silence the step-by-step trace (on by default)"
	@echo "  WAKE_BUDGET=n  override the per-check budget, in seconds"
	@echo "  the raw terminal stream of each run is left beside its workspace"
	@echo ""
	@echo "Where a live run leaves its output:"
	@echo "  test-runs/<target>_<timestamp>/<test>/  scratch repo, state, pty log"
	@echo "  test-runs/latest, test-runs/latest-<target>  symlinks to the newest"
	@echo "  every run keeps its own directory; nothing is overwritten"
	@echo ""
	@echo "make lint        run ruff"
	@echo "make fmt         apply ruff formatting fixes"
	@echo "make validate    validate the plugin and marketplace manifests with the Claude CLI"
	@echo "make check       test + lint + validate"
	@echo "make clean       remove caches and test-runs/, then clean-claude"
	@echo "make clean-claude  remove the ~/.claude/projects entries that test runs"
	@echo "                   leave behind, outside the repository where 'clean'"
	@echo "                   cannot reach them"

ifeq ($(UV),)
test smoke smoke-auto wake wake-memory wake-repeat test-harness lint fmt clean clean-claude:
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
# workspace is left under test-runs/smoke_<timestamp>/ afterwards so a failure
# can be inspected — and is still there after the next run, of any target.
smoke: TEST_RUN_LABEL := smoke
smoke:
	uv run --group dev pytest -m smoke -s -v -rs

smoke-auto: TEST_RUN_LABEL := smoke-auto
smoke-auto:
	SMOKE_SKIP_INTERACTIVE=1 uv run --group dev pytest -m smoke -s -v -rs

# Spec-0002. Automates the one smoke check a person otherwise confirms, by
# driving a real interactive session on a pseudo-terminal. Opt-in on purpose:
# it spends model usage on two real reviews, and it is the component here most
# exposed to changes in the terminal interface, so it never gates anything.
wake: TEST_RUN_LABEL := wake
wake:
	uv run --group dev pytest -m "pty and not auto_memory" -s -v -rs

# The same exchange with Claude Code's own auto memory left on, which the wake
# check deliberately disables. Auto memory records the lesson during the turn
# that teaches it, so this plugin's reviewer finds it already owned and declines
# — correct behavior that would nonetheless read as a broken wake. Separate
# target because it is a third live session, and because what it observes is the
# interaction rather than the wake.
wake-memory: TEST_RUN_LABEL := wake-memory
wake-memory:
	uv run --group dev pytest -m "pty and auto_memory" -s -v -rs

# A self-check of the harness, not of the plugin — which is why it is named for
# the harness and not for the wake. It drives the same PtySession against a fake
# terminal that only echoes what it captured, so a stalled live run can be
# attributed: if this passes, input is being delivered and turn boundaries are
# being detected, and the stall is in the session under test.
#
# No model and no cost, so these are ordinary tests and run inside `make test`
# like everything else. This target only reruns them alone with the trace on,
# which is what you want mid-debugging.
test-harness:
	uv run --group dev pytest -m harness -s -v -rs

# Acceptance criterion 1: reliable across ten consecutive runs. Stops at the
# first failure, since that is the answer.
#
# Each iteration is its own pytest process and so claims its own directory under
# test-runs/. Numbering the label as well as stamping the time is what makes the
# ten sort in the order they ran, so the third of ten can be found without
# reading timestamps — which is the run you want when the loop stops at it.
wake-repeat:
	@for run in 1 2 3 4 5 6 7 8 9 10; do \
	  echo "=== wake run $$run/10 ==="; \
	  TEST_RUN_LABEL=wake-repeat-$$(printf '%02d' $$run) \
	    uv run --group dev pytest -m "pty and not auto_memory" -q -rs || exit 1; \
	done
	@echo "=== ten consecutive wake runs, no failures ==="

lint:
	uv run --group dev ruff check plugin tests

fmt:
	uv run --group dev ruff check --fix plugin tests

clean:
	rm -rf .pytest_cache .ruff_cache test-runs tmp/smoke
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@$(MAKE) --no-print-directory clean-claude

# Claude Code keeps its own transcripts and memories for a working directory in
# ~/.claude/projects/<mangled-path>/, and every live run works in a directory
# nothing has used before — which is what stops a run inheriting the previous
# one's memory of the lesson under test, and what leaves one small directory
# behind per run. They are outside the repository, so `clean` cannot reach them
# by removing files; this is how they go.
#
# It prints every path before deleting it. Deleting outside the repository has
# to be readable afterwards rather than taken on trust in a matching rule.
clean-claude:
	uv run python -m tests.smoke.workspaces
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
	@claude plugin validate .

check: test lint validate
