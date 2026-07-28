# Claude Self-Improvement

A private Claude Code plugin and local learning engine that turn verified corrections and hard-won workflows into durable, reviewable memory, rules, skills, and hooks.

The project targets the local Claude Code runtime shared by:

- the standalone Claude Code CLI;
- the Claude Code extension for VS Code; and
- the Code tab in Claude Desktop when the environment is **Local**.

Ordinary Claude Desktop Chat, Cowork/cloud sessions, SSH sessions, and devcontainers have different configuration and filesystem boundaries. They are deliberately deferred to Phase 4.

## Status

Design and specifications only. No runtime implementation has been accepted yet.

## First releasable vertical slice

> Complete a substantial task in one local Claude Code surface, capture one legitimate reusable lesson, produce and approve a reversible patch, then verify that the lesson is applied in a fresh session opened from a different local Claude Code surface.

## Design principles

- Evidence before persistence.
- Memory for durable facts; skills for procedures; hooks for deterministic enforcement.
- Search and patch before creating a new artifact.
- Human-authored content is never silently rewritten.
- Automatic changes are limited to low-risk, agent-owned artifacts.
- Every mutation is validated, backed up, attributable, and reversible.
- Temporary task state, completion logs, commit identifiers, and unverified guesses are not durable learning.

## Specifications

See [`docs/specs/README.md`](docs/specs/README.md) for the normative specification index:

1. [Initial system design](docs/specs/0001-initial-system-design.md)
2. [Phase 1 — Review-only vertical slice](docs/specs/0002-phase-1-review-only.md)
3. [Phase 2 — Trusted automatic updates](docs/specs/0003-phase-2-trusted-automatic-updates.md)
4. [Phase 3 — Skill curator](docs/specs/0004-phase-3-skill-curator.md)
5. [Phase 4 — Additional execution environments](docs/specs/0005-phase-4-additional-environments.md)

## Intended repository layout

```text
claude-self-improvement/
├── .claude-plugin/plugin.json
├── agents/
├── bin/claude-si-hook
├── hooks/hooks.json
├── skills/
├── cmd/claude-si/
├── internal/
├── dist/                 # generated packaged artifacts
├── tests/
├── docs/specs/
└── README.md
```

The implementation layout is proposed by Spec-0001 and may change through an explicit design amendment before Phase 1 begins.

## Authoritative platform documentation

- [Claude Code plugins](https://code.claude.com/docs/en/plugins)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Skills](https://code.claude.com/docs/en/skills)
- [Memory](https://code.claude.com/docs/en/memory)
- [VS Code extension](https://code.claude.com/docs/en/vs-code)
- [Claude Desktop Code tab](https://code.claude.com/docs/en/desktop)

## License

No license has been selected. The repository is private; all rights are reserved until a license is added explicitly.
