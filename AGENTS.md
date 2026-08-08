# Agent instructions

## Scope

This repository develops a self-improvement plugin and local learning engine for Claude Code surfaces.

## Source of truth

- The current normative target is `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.
- Earlier architecture and phase documents under `docs/hypothetical-extensions/specs/` are non-normative research material.
- Current Claude Code behavior must be checked against official documentation at `https://code.claude.com/docs/` before implementation relies on it.

## Specification status

**Never mark a specification, slice, or acceptance criterion as done, implemented, complete, or passing without having first observed the evidence for it in this session.** Evidence means a command that ran and a result that was read: a passing test, an observed output, a verified artifact. Code being written is not evidence. Tests existing is not evidence. A run that was started, skipped, timed out, or interrupted is not evidence.

Where evidence is partial, say exactly which part is covered and which is not, in the status line itself. A specification whose checks have never passed is `Implemented; unverified`, not `Implemented`. Downgrade a status the moment its evidence is invalidated.

## New findings get their own specification

- A question a specification did not scope goes in a new numbered one. The original is **not edited** — no summary, no section, no forward link. Its status line is the only exception, and only if its own acceptance criteria are affected. References point newer to older. Worked example: Spec-0002 raised it, Spec-0005 carries it.
- A finding specification is not a design. It states the measurement, each hypothesis already eliminated and what eliminated it, what would settle it, how it was found, and what closing looks like — including "not worth the cost", recorded as a decision rather than left to lapse.
- Do not build instrumentation for a question nobody has framed. Work proposed to answer an open finding stays behind a named hypothesis its output could confirm or kill.

## Development rules

- Deliver the Hermes-style experiential-learning vertical slice before introducing hypothetical extensions.
- Complete the user's task before learning review; review failure must not invalidate completed work.
- Ordinary experiential learning must not require user-authored behavioral test suites.
- Never infer that Claude surfaces share a filesystem, home directory, plugin cache, or process.
- Do not write directly to Claude configuration, memory, skill, or hook files without exact review, backup, and rollback.
- Treat Claude-managed auto-memory as read-only until Anthropic documents a supported external mutation contract.
- Do not store prompts, assistant responses, credentials, environment variables, or transcript bodies in telemetry.
- Use redacted fixtures in tests. Never copy live Claude transcripts or authentication state into the repository.
- Prefer deterministic classification filters before invoking an LLM reviewer.
- Search for and patch an existing artifact before creating a new skill or rule.
- Human-authored artifacts remain review-only.
- Use conventional commits.
- Commit at checkpoints as meaningful progress is achieved, rather than accumulating a whole task into one commit at the end.
- Add executable acceptance tests for every MVP behavioral requirement.

## Working environment

NEVER use the `$TMPDIR` environment variable. Use `./.tmp` (relative to the repository root)
for scratch files; create it if it does not exist.

NEVER use the GitHub API or GitHub MCP tools to update branch refs or push branch contents.
Use local git branch workflows; if push authentication is unavailable, stop and report the
blocker rather than updating the branch remotely.

NEVER change git config at the local or global level unless explicitly instructed, and never
switch or change a remote.

- **Use `uv` for Python.** Run project commands through `uv run` or the `Makefile` targets;
  sync with `.devcontainer/scripts/uv-sync.sh` (or `uv sync`) after changing dependencies.
  Never install packages globally.
- **Scope test runs narrowly** while iterating: `uv run --group dev pytest <path>::<test_name>`.
  Run `make test` when a whole-suite answer is needed. `make smoke`, `make wake`, and
  `make wake-memory` spend real model usage and are never run unprompted.
- **Escalate to a container when the host lacks the toolchain — never give up after a local
  failure.** If `uv` is missing or a command needs the provisioned image, escalate in this
  order: (a) Docker daemon available → use the `/agentdev:microvm-sandbox` skill to run the
  command through `devcontainer exec`; (b) no Docker daemon → use the
  `/agentdev:remote-codespace-session` skill to run it on a GitHub Codespace over SSH. Only
  report a blocker if both escalation paths are unavailable.
- **For yes/no and multiple-choice questions, prefer the assistant's structured-question
  tool** over free text (VS Code Copilot: `vscode/askQuestions`; Claude Code:
  `AskUserQuestion`).
- Keep devcontainer-related scripts in `.devcontainer/scripts`.

### When in doubt

Consult the **Principal Engineer** agent supplied by the `agentdev` catalog for architecture,
design decisions, and implementation strategies.

## Coding conventions

### Python

- Follow **PEP 8**: 4 spaces per indentation level, descriptive names. The line limit is
  **99** (`.ruff.toml`), not 79.
- The plugin runtime targets Python 3.9 (`requires-python` in `pyproject.toml`), so 3.10+
  syntax and typing idioms are unavailable in `plugin/`.
- Use type hints (PEP 484) and PEP 257 docstrings placed immediately after `def`/`class`.
- Formatting and autofixes come from **ruff**, through the pre-commit hooks. Verify with
  `python-lint-check.sh` from the `agentdev` catalog for a fast, Docker-free check. Never
  judge style with stock `flake8` or `black`: their defaults (79-char limit, double quotes,
  different isort grouping) produce false positives that do not match this repository. Full
  workflow in the `/agentdev:python-format-lint` skill.
- **Exception handling**: never write empty handlers (`except ...: pass`). Handle expected
  exceptions explicitly by at least one of: logging context, returning a safe fallback value,
  re-raising with context, or raising `SystemExit` for CLI interruption paths. If an
  exception must be intentionally ignored, document the reason in a comment and keep the
  ignored scope minimal. Prefer specific exception types over broad `except Exception`.
  Hook scripts that must fail open are the deliberate exception and say so at the handler.

### Python testing

- **Always use `pytest`** — never `unittest` (fixture strings that generate a sample project
  for a live run are not test code).
- Prefer multiple smaller, focused test files over large monolithic ones.
- Keep fixtures independent of repository identity when the behavior under test is meant to
  work in other repositories or installed plugins.
- Import values that belong to the tested contract from the code under test instead of
  restating them as literals.

### Shell

- All scripts are `#!/usr/bin/env bash` with `set -euo pipefail`, and must pass `shellcheck`
  (enforced by pre-commit).
- Quote every expansion; prefer `"${var:-default}"` over assuming a variable is set.

**Edit `AGENTS.md`; `CLAUDE.md` only includes it (`@AGENTS.md`), so changes there cover all
agents.**

## Documentation consistency

When the MVP changes, update together:

- `README.md`;
- `docs/specs/README.md`; and
- `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.

Do not rewrite hypothetical extension specifications merely to match the MVP. Validate relative Markdown links before committing.

## Debugging

When running `make wake` always capture output to a file, running it costs real money.
