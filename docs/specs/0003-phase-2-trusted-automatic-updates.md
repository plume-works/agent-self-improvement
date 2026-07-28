# Spec-0003: Phase 2 — Existing-artifact patches and trusted automatic updates

- **Status:** Proposed
- **Date:** 2026-07-28
- **Target releases:** `v0.2` (Phase 2A), `v0.2.1` (Phase 2B)
- **Depends on:** The packaged `v0.1` core and the surface certification where the feature will run

## Summary

Phase 2 is split into two independently gated releases:

- **Phase 2A / `v0.2`:** user-approved patches to existing non-auto-memory artifacts.
- **Phase 2B / `v0.2.1`:** narrowly trusted automatic patches to unchanged, explicitly agent-managed artifacts.

Unattended writes cannot ship until reviewed existing-file mutation has passed crash, external-writer, recovery, and rollback gates from the packaged artifact.

## Phase 2A: reviewed existing-artifact patches

### Supported targets

After explicit user or project enrollment, Phase 2A may propose and patch:

- personal skills under `~/.claude/skills/`;
- project skills under `.claude/skills/`;
- user `~/.claude/CLAUDE.md`;
- project `CLAUDE.md` or `.claude/CLAUDE.md`; and
- project `.claude/rules/*.md`.

It does not mutate:

- Claude-managed auto-memory;
- settings, permissions, hooks, MCP configuration, agents, or executables;
- authentication or trust state; or
- files outside an enrolled destination root.

### Project authorization registry

Project mutation requires an engine-owned authorization record containing:

- canonical repository identity and root;
- explicit user enrollment timestamp;
- allowed destination classes;
- ownership defaults;
- expiry or revocation state; and
- canonical-path and filesystem-identity data needed to detect root replacement.

Claude `cwd`, workspace trust UI, project plugin enablement, and authenticated invocation are not authorization.

### External writers and race limits

The engine lock coordinates only `claude-si`. Editors, Git, Claude Code, and other processes may change the target concurrently. The engine therefore offers best-effort conflict avoidance, not filesystem compare-and-swap:

1. proposal records the base hash and canonical identity;
2. approval re-reads and re-renders the exact diff;
3. apply acquires the engine lock and rechecks the target;
4. a `prepared` journal entry is written;
5. source credentials are scanned before the recovery copy;
6. a randomly named recovery copy is written and synced;
7. a same-directory temporary file is written and synced;
8. the target is rechecked immediately before rename;
9. rename and parent-directory sync occur;
10. installed bytes are validated and compared to intended hashes; and
11. metadata is marked applied only after observation.

Unexpected bytes at any recovery point produce `conflict`. The engine never overwrites an unexpected external edit automatically.

Rollback is a new journaled mutation from the current expected hash to the prior bytes. A changed current target causes a conflict requiring review.

### Ownership at approval

Every created or materially rewritten artifact has an explicit ownership choice:

- `human-owned-after-creation` — default;
- `agent-managed` — opt-in for possible Phase 2B eligibility;
- `mixed` — automatically assigned after an external edit to an agent-managed artifact; or
- `unknown` — no valid provenance.

Approval by itself does not make an artifact agent-managed.

### Phase 2A acceptance gate

From the exact checksummed release artifact:

1. `claude plugin validate --strict` succeeds without unexpected warnings.
2. Plugin and engine version handshake succeeds.
3. Each destination class passes a user-approved proposal, rejection, apply, reload, recovery, and rollback test.
4. Project writes fail until explicit enrollment and fail after revocation/expiry.
5. `cwd` and plugin enablement cannot substitute for enrollment.
6. External changes before approval, before lock, immediately before rename, after rename, and before journal commit produce the specified observed state without silent overwrite.
7. Crash injection at every journal boundary reconciles from actual bytes.
8. Rollback is journaled and refuses changed current content.
9. Auto-memory and forbidden configuration classes remain unreachable through path aliases and symlinks.
10. Secret canaries in source, proposal, logs, SQLite, recovery, diagnostics, and journal output are rejected or absent as specified.
11. Success, rejection, cancellation, reload, uninstall, and recovery are exercised through the packaged plugin and real executable path.

## Phase 2B: trusted automatic updates

Phase 2B permits a narrow class of low-risk candidates to patch existing agent-managed artifacts automatically. It keeps the proposal, policy, mutation journal, recovery, provenance, conflict, and rollback pipeline from Phase 2A.

### Security invariant

An automatic update is allowed only when every required predicate is positively proven. Missing provenance, ambiguous ownership, external changes, uncertain scope, validation warnings, or policy disagreement fail closed to manual review.

### Eligibility policy

A candidate may be auto-applied only when all of the following are true:

1. The target carries valid provenance and the user explicitly chose `agent-managed`.
2. The current hash matches the last observed engine mutation.
3. The candidate patches one existing artifact; it does not create a new global artifact.
4. Classification is `memory`, `rule`, or `skill`; never `hook`.
5. Scope is an already enrolled user or project scope.
6. The patch does not alter frontmatter permissions, tool grants, hooks, MCP configuration, shell commands, external URLs, or executables.
7. No secret, credential-shaped string, personal data, or transcript excerpt survives redaction.
8. Evidence contains a verified success or explicit user correction from a supported capture path.
9. The candidate matches exactly one existing artifact above the configured confidence threshold.
10. All validators pass with no warnings.
11. Recovery data is durable before replacement.
12. Per-session and per-day automatic mutation budgets remain available.

Any failed predicate routes to `needs_review` with machine-readable reasons.

### Permanently review-only changes

The following remain review-only:

- creating a new skill, rule, or memory file;
- editing human, mixed, or unknown-ownership content;
- changing global `CLAUDE.md` behavior;
- changing settings, permissions, hooks, MCP servers, agents, or plugin configuration;
- adding or modifying executables or external URLs;
- deleting or archiving an artifact;
- moving knowledge between user and project scope;
- resolving contradictory instructions; and
- writing after an external change invalidates the proposal.

### User controls

The user can:

- disable automatic updates globally or for one project;
- restrict eligible destinations;
- set daily and per-session budgets;
- inspect every automatic mutation;
- roll back one mutation through the journal;
- revert all eligible mutations from one session when no conflicts exist; and
- convert an agent-managed artifact to human ownership.

Automatic updates are disabled after upgrade until explicitly enabled.

### Failure behavior

- Policy parser failure disables automatic updates.
- Unknown schema versions fail closed.
- Lock contention queues or defers; it never bypasses the lock.
- Recovery preparation failure prevents the write.
- Nonterminal journal entries reconcile before any later mutation.
- Unexpected installed bytes create a conflict and disable automatic mutation for that artifact.
- A repeated failure moves the candidate to review rather than retrying indefinitely.

### Phase 2B acceptance gate

From the exact checksummed release artifact:

1. Every Phase 2A gate continues to pass.
2. Automatic updates remain disabled until explicitly enabled.
3. A qualifying patch to an unchanged agent-managed skill applies without a prompt.
4. The same patch against human, mixed, unknown, externally changed, or unenrolled content requires review.
5. New artifacts, hooks, executables, URLs, and scope changes require review.
6. Mutation budgets stop further automatic writes and queue candidates for review.
7. Crash injection at every journal boundary reconciles from actual filesystem hashes.
8. Concurrent external writes never result in the engine claiming an unobserved state as applied.
9. Every automatic mutation is attributable and rollback is a new journaled mutation.
10. The new automatic path—not only prior release behavior—is exercised through the installed plugin cache, real executable, reload, cancellation, crash recovery, uninstall, and fresh-session verification.
11. Fuzz/property tests cannot escape enrolled roots through traversal, symlinks, case normalization, Unicode normalization, or root replacement.

## Non-goals

Phase 2 does not:

- directly mutate Claude-managed auto-memory;
- auto-create new skills;
- auto-edit hooks or settings;
- auto-resolve contradictions;
- archive stale skills;
- synchronize between machines or containers; or
- use an LLM decision as the sole authorization for a write.
