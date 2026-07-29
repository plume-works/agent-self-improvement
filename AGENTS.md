# Agent instructions

## Scope

This repository develops a self-improvement plugin and local learning engine for Claude Code surfaces.

## Source of truth

- The current normative target is `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.
- Earlier architecture and phase documents under `docs/hypothetical-extensions/specs/` are non-normative research material.
- Current Claude Code behavior must be checked against official documentation at `https://code.claude.com/docs/` before implementation relies on it.

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
