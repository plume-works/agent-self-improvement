# Claude Self-Improvement

A private Claude Code plugin and local learning engine that turn verified corrections and hard-won workflows into durable, reviewable memory, rules, skills, and hooks.

The long-term local target covers:

- the standalone Claude Code CLI;
- the Claude Code extension for VS Code; and
- the Code tab in Claude Desktop when the environment is **Local**.

Ordinary Claude Desktop Chat, Cowork/cloud sessions, SSH sessions, and devcontainers have different configuration and filesystem boundaries. They are deliberately deferred to Phase 4.

## Status

Design and specifications only. No runtime implementation has been accepted yet.

The surfaces are certified incrementally rather than coupled into the first release.

## First releasable vertical slice

> Explicitly invoke learning in the standalone Claude Code CLI, approve one new uniquely named personal skill, install it with journaled recovery, and verify deterministic discovery and invocation in a fresh packaged CLI session.

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
2. [Phase 1 — Review-only local core](docs/specs/0002-phase-1-review-only.md)
3. [Phase 2 — Existing-artifact patches and trusted automatic updates](docs/specs/0003-phase-2-trusted-automatic-updates.md)
4. [Phase 3 — Engine-event skill curator](docs/specs/0004-phase-3-skill-curator.md)
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
