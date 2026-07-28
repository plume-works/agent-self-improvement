# Spec-0005: Phase 4 — Additional execution environments

- **Status:** Proposed, intentionally deferred
- **Date:** 2026-07-28
- **Depends on:** Each adapter names only the packaged core contracts and topology seams it consumes
- **Release model:** Independent environment adapters; no single coupled Phase 4 release

## Summary

Claude's surfaces do not all share the Mac's local Claude Code process, home directory, plugin cache, hooks, or memory. Phase 4 extends the system only after mapping each environment's real ownership and trust boundaries.

The local `v0.1`–`v0.3` release remains useful if every Phase 4 adapter is absent or disabled.

## Environment matrix

| Environment | Agent runtime | Knowledge source | Main gap |
| --- | --- | --- | --- |
| Desktop Code, Local | Mac | Mac `~/.claude` and project files | Covered before Phase 4 |
| VS Code devcontainer | Container extension host/runtime | Container home and mounted project | Personal store/plugin not inherently present |
| Desktop Code over SSH | Remote host | Remote `~/.claude` | Mac store is not remote store |
| Desktop Chat | Anthropic app runtime plus connectors | Account/app configuration | No Claude Code lifecycle hooks |
| Cowork/cloud | Anthropic-hosted or isolated runtime | Account-synced skills and cloned project | Does not read Mac `~/.claude/skills` |

## Track A: VS Code devcontainers

**Depends on:** Packaged `v0.1` proposal/install/recovery contracts, a Linux engine artifact, and the devcontainer topology seam gate. Automatic updates and curation are not prerequisites.

### Required topology decision

Before implementation, verify whether the active VS Code Claude extension executes in the local UI host or remote container extension host for the supported version. Record where it resolves:

- `$HOME` and `~/.claude`;
- plugin installations;
- hook commands;
- project paths;
- engine binary architecture;
- authentication state; and
- network endpoints.

### Preferred design

Use three layers:

1. Commit project knowledge and project plugin declarations where team/repository scope is appropriate.
2. Install a Linux build of the plugin and engine inside the container for local hook execution.
3. Optionally connect to a narrowly authenticated Mac-side personal knowledge service for user-scoped candidate search and proposals.

Do not bind-mount the entire Mac `~/.claude` directory. It contains authentication, trust state, caches, and machine-specific configuration that must not be exposed wholesale to a development container.

### Security requirements

- Separate runtime identity per container.
- Explicit project allowlist for access to Mac-side personal knowledge.
- Operation-level API; no arbitrary filesystem path parameter.
- No credential forwarding.
- Bounded request size, deadlines, cancellation, and audit IDs.
- Deny writes by default; enable only after path and ownership mapping is proven.
- Suppress duplicate mutation authority: either the container engine or Mac service owns a given mutation, never both.

### Acceptance gate

A devcontainer adapter ships only when:

1. A clean representative container installs the correct architecture build reproducibly.
2. Project candidates remain project-scoped.
3. Personal knowledge access, if enabled, uses authenticated outbound connectivity.
4. The container cannot read Mac Claude credentials or unrelated personal files.
5. Concurrent host/container proposals cannot corrupt or race one target.
6. Disconnecting the Mac service fails closed without blocking Claude.
7. Uninstalling the adapter leaves the local Mac release unaffected.

## Track B: Desktop Code over SSH

**Depends on:** Packaged `v0.1` proposal/install/recovery contracts plus remote installation and state-location verification. Automatic updates and curation are not prerequisites.

SSH sessions read configuration from the remote host. The adapter therefore installs and stores state remotely unless a separate authenticated service is explicitly configured.

Requirements:

- remote plugin/engine installation is independent and versioned;
- remote project paths never resolve on the Mac by assumption;
- candidate provenance identifies the remote host without exposing it in shared telemetry;
- no automatic cross-host user-memory merge; and
- synchronization conflicts require review.

## Track C: Desktop Chat

**Depends on:** The proposal context/submission protocol from `v0.1` plus verified MCPB packaging. It does not require filesystem mutation, automatic updates, or curation.

Desktop Chat does not expose the Claude Code hook lifecycle. Integration, if desired, shall use a local MCP desktop extension (`.mcpb`) exposing narrow tools such as:

- search approved knowledge;
- submit a candidate;
- inspect candidate status; and
- request a proposed patch.

Desktop Chat shall not receive a general-purpose filesystem mutation tool. Candidate submission from Chat enters the same review policy as any other untrusted source.

The MCP extension owns local process packaging and transport. The learning engine remains the sole owner of durable state and mutations.

## Track D: Cowork and cloud sessions

**Depends on:** The versioned artifact export format plus a verified public account/project import seam, if one exists. It does not require Phases 2 or 3.

Cowork and cloud sessions use account-synchronized skills and/or project skills from cloned repositories rather than the Mac's personal `~/.claude/skills`.

Before implementing synchronization, verify Anthropic's supported account-level skill APIs or export/import mechanisms. If no public write API exists, the feature remains manual. Browser automation against private account settings is not an acceptable persistence API.

Allowed initial behavior:

- export a reviewable skill bundle;
- commit project skills to the repository; or
- instruct the user how to enable a skill through Claude's Customize UI.

No feature may claim automatic Cowork persistence without a verified public seam.

## Shared synchronization rules

If later adapters synchronize knowledge:

- artifact IDs remain stable across copies;
- each mutation has one origin and parent hash;
- divergent edits create a conflict, not last-writer-wins overwrite;
- scope never broadens automatically;
- user and project stores remain distinct;
- secrets and raw transcripts never synchronize; and
- deletion is represented as a reversible proposal, not silently propagated.

## Non-goals

Phase 4 does not promise:

- one transparent global filesystem;
- automatic replication of all personal knowledge;
- credential sharing between Mac, containers, SSH hosts, and cloud;
- support for undocumented Claude internals;
- equivalent lifecycle hooks in Desktop Chat or Cowork; or
- a mandatory cloud control plane.
