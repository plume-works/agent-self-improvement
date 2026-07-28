# Spec-0003: Phase 2 — Trusted automatic updates

- **Status:** Proposed
- **Date:** 2026-07-28
- **Target release:** `v0.2`
- **Depends on:** The complete packaged-artifact gate in [Spec-0002](0002-phase-1-review-only.md)

## Summary

Phase 2 permits a narrow class of low-risk learning candidates to update agent-owned artifacts automatically. It does not turn every inferred lesson into an unattended write.

The system keeps the Phase 1 candidate, evidence, validation, backup, provenance, and rollback pipeline. It adds a deterministic trust policy before the mutation step.

## Security invariant

An automatic update is allowed only when every required predicate is positively proven. Missing provenance, ambiguous ownership, stale content, uncertain scope, validation warnings, or policy disagreement all fail closed to manual review.

## Eligibility policy

A candidate may be auto-applied only when all of the following are true:

1. The target artifact carries valid provenance showing it was created by this system.
2. The artifact has not been modified outside a recorded mutation since the last known hash.
3. The candidate patches an existing artifact; it does not create a new global artifact.
4. Classification is `memory`, `rule`, or `skill`; never `hook`.
5. Scope is an already trusted user or project scope.
6. The patch does not alter frontmatter permissions, tool grants, hook definitions, MCP configuration, shell commands, external URLs, or executable files.
7. No secret, credential-shaped string, personal data, or transcript excerpt survives redaction.
8. The evidence contains at least one verified success or explicit user correction.
9. The candidate matches one existing artifact with confidence above the configured threshold.
10. All validators pass with no warnings.
11. A backup is durable before replacement.
12. The per-session and per-day automatic mutation budgets are not exhausted.

Any failed predicate routes the candidate to `needs_review` with machine-readable reasons.

## Permanently review-only changes

The following require explicit approval in Phase 2:

- creating a new skill, rule, or global memory file;
- editing any human-authored or unknown-provenance artifact;
- changing `CLAUDE.md` instructions that apply to all projects;
- changing settings, permissions, hooks, MCP servers, agents, or plugin configuration;
- adding or modifying executable commands;
- deleting or archiving an artifact;
- moving knowledge between user and project scope;
- resolving contradictory instructions; and
- writing after an external modification invalidates the proposal.

## Provenance

Agent-owned artifacts shall carry a non-executable provenance record containing:

- stable artifact ID;
- creator `claude-self-improvement`;
- schema version;
- creation mutation ID;
- last mutation ID;
- prior and resulting content hashes; and
- ownership state: `agent`, `human`, or `mixed`.

Provenance may use frontmatter when supported without changing skill semantics. Otherwise it shall use a sidecar keyed by canonical path and content hash. Sidecars never override the actual file contents.

If a human edits an agent-owned artifact outside the engine, ownership becomes `mixed` and future mutations require review.

## Automatic workflow

```text
candidate reviewed
      |
      v
eligibility predicates
  | pass       | fail/unknown
  v            v
budget check   needs_review
  |
  v
lock + stale check
  |
  v
backup + atomic write
  |
  v
post-write validation
  | pass       | fail
  v            v
applied       restore + failed
```

## User controls

The user shall be able to:

- disable automatic updates globally;
- disable them for one project;
- restrict eligible destinations;
- set daily and per-session budgets;
- inspect every auto-applied mutation;
- revert one mutation;
- revert all automatic mutations from a session; and
- convert an agent-owned artifact to human-owned.

The default immediately after upgrade from Phase 1 is **automatic updates disabled**. Enabling requires an explicit user action.

## Failure behavior

- Policy parser failure disables automatic updates.
- Unknown schema versions fail closed.
- Lock contention queues or defers; it never bypasses the lock.
- Backup failure prevents the write.
- Post-write validation failure restores the prior bytes.
- Restore failure disables further mutation and raises a high-priority local diagnostic.
- A repeated failure for the same candidate moves it to review rather than retrying indefinitely.

## Acceptance gate

Phase 2 is complete only when:

1. All Phase 1 acceptance tests continue to pass.
2. Automatic updates remain disabled after upgrade until explicitly enabled.
3. A qualifying patch to an untouched agent-owned skill applies without a prompt.
4. The same patch against human-authored, mixed, or unknown-provenance content requires review.
5. New skills, hooks, executable changes, and scope changes require review.
6. External edits invalidate automatic eligibility.
7. Mutation budgets stop further automatic writes and queue candidates for review.
8. Simulated interruption at every write step preserves either the old or complete new file, never a partial file.
9. Every mutation is attributable and reversible.
10. Rollback is verified from a fresh Claude Code session.
11. Fuzz and property tests cannot escape approved roots through traversal, symlinks, or case-normalization differences.

## Non-goals

Phase 2 does not:

- auto-create new skills;
- auto-edit hooks or settings;
- auto-resolve contradictions;
- archive stale skills;
- synchronize between machines or containers; or
- use an LLM decision as the sole authorization for a write.
