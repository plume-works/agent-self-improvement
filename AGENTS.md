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
- Add executable acceptance tests for every MVP behavioral requirement.

## Documentation consistency

When the MVP changes, update together:

- `README.md`;
- `docs/specs/README.md`; and
- `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.

Do not rewrite hypothetical extension specifications merely to match the MVP. Validate relative Markdown links before committing.

## Debugging

When running `make wake` always capture output to a file, running it costs real money.
