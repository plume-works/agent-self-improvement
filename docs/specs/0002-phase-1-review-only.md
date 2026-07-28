# Spec-0002: Phase 1 — Review-only vertical slice

- **Status:** Proposed
- **Date:** 2026-07-28
- **Target release:** `v0.1`
- **Depends on:** [Spec-0001](0001-initial-system-design.md)
- **Supported topology:** macOS local Claude Code runtime

## Summary

Phase 1 proves the entire learning loop without permitting unattended changes to durable Claude knowledge.

A substantial task completed in one supported local surface can produce a candidate lesson. The engine classifies it, searches existing artifacts, and prepares a concrete proposed patch. Anton explicitly approves the proposal. The engine then applies it atomically with a backup and verifies that a fresh session in a second local surface can discover and use the lesson.

## User-visible result

The user can:

1. inspect queued learning candidates;
2. see why each candidate was captured;
3. see the proposed destination and exact diff;
4. approve or reject the candidate;
5. roll back an approved mutation; and
6. verify the resulting memory, rule, or skill from another local Claude Code surface.

## Included surfaces

| Surface | Phase 1 support |
| --- | --- |
| Standalone Claude Code CLI | Required |
| VS Code Claude Code extension, local workspace | Required |
| Claude Desktop Code tab, Local environment | Required |
| Claude Desktop Chat | Excluded |
| Cowork/cloud sessions | Excluded |
| SSH sessions | Excluded |
| VS Code devcontainer | Excluded |

## Functional requirements

### Plugin packaging

The repository shall contain a valid Claude Code plugin with:

- `.claude-plugin/plugin.json`;
- a model-invocable `self-improvement` skill containing the learning policy;
- user-invocable review, reject, apply, status, and rollback commands or skills;
- a learning-reviewer agent that may call read-only engine discovery/review commands but cannot mutate Claude knowledge artifacts;
- a `Stop` hook that invokes the deterministic candidate detector; and
- executable wrappers that locate the local `claude-si` engine without embedding secrets.

The plugin shall install at user scope and load in all three required local surfaces.

### Candidate detection

The `Stop` hook shall be fast and deterministic. It may inspect only the hook event, bounded metadata available from the transcript path, and existing local state. It shall not call an LLM itself.

The detector shall enqueue a candidate only when at least one high-signal condition exists:

- the user corrected Claude;
- a tool or command failed and a later attempt verified a different working method;
- an invoked skill was demonstrably incomplete or incorrect;
- the task crossed a configurable complexity threshold; or
- the user explicitly asked Claude to remember or reuse something.

The detector shall suppress:

- empty and trivial turns;
- repeated stop events for the same turn;
- candidates already rejected for the same evidence fingerprint;
- secrets or credential-shaped evidence;
- raw transcript bodies in the persistent index.

### Review

Candidate review shall be explicit. The reviewer produces:

- a one-sentence proposed lesson;
- evidence references that identify the session and event without copying sensitive bodies into telemetry;
- confidence and rationale;
- classification: `memory`, `rule`, `skill`, `hook`, or `discard`;
- scope: `user`, `project`, or `local`;
- matching existing artifacts;
- the exact proposed diff; and
- risk flags.

Phase 1 never applies a candidate before user approval.

### Mutation

Approved writes shall:

1. acquire an exclusive mutation lock;
2. re-read the current target and reject stale proposals;
3. validate destination and scope;
4. create a content-addressed backup in the same trust boundary;
5. write a temporary file in the destination directory;
6. flush and atomically rename it;
7. validate the resulting artifact;
8. record provenance and hashes; and
9. expose a rollback identifier.

Project artifacts may be changed only inside the active trusted project. User artifacts may be changed only under documented Claude user configuration paths. Phase 1 shall not modify `~/.claude/settings.json`, hooks, permissions, MCP configuration, authentication state, or `~/.claude.json`.

### Supported destinations

Phase 1 may propose and, after approval, mutate:

- `~/.claude/CLAUDE.md`;
- project `CLAUDE.md` or `.claude/CLAUDE.md`;
- `.claude/rules/*.md`;
- personal skills under `~/.claude/skills/`; and
- project skills under `.claude/skills/`.

Claude-managed auto-memory may be searched read-only for duplicate detection, but the engine does not write its files because no supported external mutation contract has been verified. Hook candidates remain proposals documented for manual implementation; Phase 1 does not install or edit hooks.

### Commands

The engine shall expose stable machine-readable commands equivalent to:

```text
claude-si candidate capture
claude-si candidate list --json
claude-si candidate show <id> --json
claude-si candidate review <id> --json
claude-si candidate reject <id> --reason <text>
claude-si candidate apply <id>
claude-si mutation rollback <mutation-id>
claude-si status --json
claude-si doctor --json
```

Human-facing plugin skills may wrap these commands but shall not scrape prose output when JSON is available.

## Data and privacy requirements

- Default storage root: `~/Library/Application Support/claude-self-improvement/` on macOS, with a configurable override for tests.
- Store normalized candidate summaries and cryptographic fingerprints, not complete transcripts.
- Never store Claude OAuth state, API keys, environment-variable values, `.env` contents, or MCP credentials.
- Redact known credential patterns before any candidate content is persisted.
- File permissions shall be user-only where the platform supports POSIX modes.
- Logs shall contain IDs, state transitions, durations, and error classes—not prompt or response text.

## Failure behavior

- Hook failure never blocks Claude from completing a response.
- Corrupt or unavailable local state disables capture and emits a local diagnostic.
- A stale proposal is returned to `needs_review`; it is never force-applied.
- Validation failure restores or preserves the previous target and marks the mutation failed.
- Surface-specific plugin load failure does not alter existing knowledge artifacts.

## Implementation sequence

1. Pin minimum supported Claude Code and macOS versions after seam tests.
2. Scaffold and validate the plugin package.
3. Implement the engine state model and deterministic redaction.
4. Implement candidate capture and deduplication from recorded hook fixtures.
5. Implement artifact discovery and classification policy.
6. Implement diff generation without write permission.
7. Implement approval-gated atomic mutation and rollback.
8. Add plugin commands and reviewer agent.
9. Exercise the packaged plugin in CLI.
10. Exercise the same installation in VS Code.
11. Exercise the same installation in Desktop Code Local.
12. Complete the cross-surface learning test.

## Deterministic test gate

The following must pass offline:

- hook input schema fixtures for supported Claude Code versions;
- capture/no-capture signal tests;
- secret and PII redaction tests;
- candidate deduplication tests;
- classification routing tests;
- existing-artifact search tests;
- stale-diff rejection tests;
- concurrent lock tests;
- atomic-write interruption tests;
- backup and rollback tests;
- path traversal and symlink escape tests;
- human-authored artifact approval tests;
- JSON CLI schema tests; and
- plugin manifest and Markdown-link validation.

## Packaged-artifact acceptance gate

Phase 1 is complete only when all of these are observed with the packaged plugin, not a source-tree shortcut:

1. `claude plugin validate` or the current official validator accepts the plugin.
2. User-scope installation succeeds on the target Mac.
3. The same installation appears in CLI, VS Code, and Desktop Code Local.
4. A substantial fixture task in Surface A creates exactly one candidate.
5. The candidate proposes the correct destination and a valid diff.
6. No durable artifact changes before approval.
7. Approval creates a backup and one attributable mutation.
8. A fresh session in Surface B loads or invokes the new knowledge and follows it.
9. Rollback restores the byte-identical prior artifact.
10. A fresh session after rollback no longer sees the reverted lesson.
11. No transcript body or credential appears in the state database, backups, or logs.

## Non-goals

Phase 1 does not:

- auto-approve any learning;
- edit Claude settings, permissions, hooks, or MCP configuration;
- run a background daemon or launchd job;
- consolidate or archive existing skills;
- synchronize state through a cloud service;
- support Desktop Chat, Cowork, cloud, SSH, or devcontainers;
- publish to a public marketplace; or
- claim compatibility with untested Claude Code versions.

## Rollback

Uninstalling or disabling the plugin stops capture. Existing knowledge remains unchanged. Every applied Phase 1 mutation has an explicit rollback record. Removing the engine state requires a separate user action and is never part of plugin uninstall.
