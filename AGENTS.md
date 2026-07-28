# Agent instructions

## Scope

This repository develops a self-improvement plugin and local learning engine for Claude Code surfaces.

## Source of truth

- Normative requirements live under `docs/specs/`.
- `docs/specs/0001-initial-system-design.md` defines architecture and invariants.
- Each phase specification defines its own release gate.
- Current Claude Code behavior must be checked against official documentation at `https://code.claude.com/docs/` before implementation relies on it.

## Development rules

- Deliver a tested vertical slice before introducing later-phase abstractions.
- Treat CLI, VS Code, Desktop Local, Desktop cloud/Cowork, SSH, and devcontainers as distinct execution topologies.
- Never infer that two surfaces share a filesystem, home directory, plugin cache, or process.
- Do not write directly to Claude configuration, memory, skill, or hook files without the mutation policy and rollback path required by the current phase.
- Treat Claude-managed auto-memory as read-only until Anthropic documents a supported external mutation contract.
- Never claim that SQLite metadata and filesystem mutation commit atomically together; use a recoverable mutation journal and reconcile observed hashes.
- The first release creates one new personal skill from an explicit CLI workflow. Hooks, existing-file edits, VS Code, and Desktop are separately gated increments.
- Do not store prompts, assistant responses, credentials, environment variables, or transcript bodies in telemetry.
- Use redacted fixtures in tests. Never copy live Claude transcripts or authentication state into the repository.
- Prefer deterministic classification filters before invoking an LLM reviewer.
- Search for and patch an existing artifact before creating a new skill or rule.
- Human-authored artifacts remain review-only unless a future specification explicitly changes that invariant.
- Use conventional commits.
- Add executable acceptance tests for every behavioral requirement.

## Documentation consistency

When architecture or sequencing changes, update together:

- `README.md`;
- `docs/specs/README.md`;
- `docs/specs/0001-initial-system-design.md`; and
- every affected phase specification.

Validate relative Markdown links before committing.
