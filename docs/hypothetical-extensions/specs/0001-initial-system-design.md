# Spec-0001: Initial system design

- **Status:** Proposed
- **Date:** 2026-07-28
- **Owners:** Claude Self-Improvement maintainers
- **Target repository:** `plume-works/claude-self-improvement`
- **First release:** [Spec-0002: Phase 1 — Review-only local core](0002-phase-1-review-only.md)

## Summary

Build a Claude Code plugin and companion local engine that convert verified corrections, debugging discoveries, and reusable workflows into durable knowledge.

The design deliberately separates:

- **detection**, which notices that a reusable lesson may exist;
- **review**, which interprets evidence and proposes a destination and diff;
- **authorization**, which decides whether a write is permitted;
- **mutation**, which performs a validated, journaled, recoverable filesystem change; and
- **curation**, which manages lifecycle after enough engine-owned activity evidence exists.

The first release is review-only. Automatic updates, curation, Desktop Chat/Cowork, SSH, and devcontainers are later independent capabilities.

## Problem statement

Claude Code already supports persistent `CLAUDE.md` instructions, auto-memory, skills, hooks, agents, plugins, and MCP servers. Those mechanisms do not by themselves guarantee disciplined self-improvement.

A useful self-improvement system must answer five questions safely:

1. Was anything durable actually learned?
2. Is the lesson a fact, instruction, procedure, enforced rule, or temporary task result?
3. Does an existing artifact already own this knowledge?
4. Is the proposed change supported by evidence and safe to persist?
5. Can the exact mutation be audited and reversed?

Without this policy layer, automatic memory tends to accumulate stale task logs, duplicate skills, weak guesses, and contradictory instructions.

## First releasable vertical slice

> In the standalone Claude Code CLI, the user explicitly invokes learning; Claude proposes one new uniquely named personal skill; the user approves it; the engine installs it with journaled recovery; and a fresh packaged CLI session deterministically discovers and invokes it.

This is the `v0.1` release boundary. Automatic hooks, existing-file edits, project scope, VS Code, and Desktop certification are separately gated increments. A plugin skeleton, candidate database, mock-only classifier, or source-tree command that writes a sample skill is not a release.

## Verified platform seams

The following seams are documented by Anthropic as of the specification date. Implementation must pin and retest them against the minimum supported Claude Code version.

| Seam | Classification | Design use |
| --- | --- | --- |
| User plugins, skills, agents, and hooks | Verified public | Package the extension at user scope |
| Plugin hooks in `hooks/hooks.json` | Verified public | Capture lifecycle signals |
| `Stop`, `PostToolUse`, `PostToolUseFailure`, `PreCompact`, `SessionStart`, and related events | Verified public | Candidate evidence and reliability tests |
| Personal and project skills | Verified public | Durable procedures |
| `CLAUDE.md` and `.claude/rules/` loading | Verified public | Durable facts and scoped instructions |
| Claude-managed auto-memory | Verified public as a Claude feature; external mutation contract not verified | Read-only duplicate discovery in Phase 1; no direct engine writes |
| Shared Claude Code settings between CLI and VS Code | Verified public | One user-scope local install |
| Shared local settings/plugins between CLI and Desktop Code Local | Verified public | Third supported surface |
| Cowork/cloud skills sourced from account/project rather than Mac personal skills | Verified public limitation | Exclude from local first release |
| Devcontainer extension-host filesystem and home resolution | Must be verified per supported topology | Defer to Phase 4 |

Authoritative references:

- [Plugins](https://code.claude.com/docs/en/plugins)
- [Plugin reference](https://code.claude.com/docs/en/plugins-reference)
- [Hooks](https://code.claude.com/docs/en/hooks)
- [Skills](https://code.claude.com/docs/en/skills)
- [Memory](https://code.claude.com/docs/en/memory)
- [VS Code](https://code.claude.com/docs/en/vs-code)
- [Desktop Code tab](https://code.claude.com/docs/en/desktop)

## Supported surfaces and scope

### Initial release

- standalone Claude Code CLI on Anton's Mac.

### Incremental local certification

- automatic hook capture (`v0.1.1`);
- VS Code Claude Code extension in a local workspace (`v0.1.2`); and
- Claude Desktop Code tab using a Local environment (`v0.1.3`).

### Deferred

- ordinary Claude Desktop Chat;
- Cowork and Claude Code cloud sessions;
- Desktop or VS Code sessions over SSH;
- VS Code devcontainers; and
- synchronization between machines.

A deferred surface must not block or weaken the local release.

## Goals

1. Capture high-signal learning opportunities with low normal-turn overhead.
2. Route durable knowledge to the correct Claude mechanism.
3. Search and patch before creating duplicate artifacts.
4. Require evidence and verification before persistence.
5. Keep human-authored content review-gated.
6. Make every write journaled, attributable, validated, recoverable, and reversible without claiming cross-store atomicity.
7. Preserve privacy by storing minimal normalized evidence rather than transcripts.
8. Certify local Claude Code surfaces incrementally after the CLI core works.
9. Fail without blocking Claude's normal work.
10. Provide deterministic tests and real packaged-artifact smoke tests.

## Non-goals

The initial architecture does not:

- replace Claude's model, session store, auto-memory implementation, or plugin manager;
- modify Claude authentication or credentials;
- persist every conversation or task result;
- make LLM judgment the sole authorization mechanism;
- silently rewrite human-authored instructions;
- enforce behavior by prompt instruction when a deterministic hook is required;
- provide a general-purpose personal knowledge graph;
- synchronize state to Anthropic, GitHub, or another cloud;
- support every Claude surface in `v0.1`; or
- guarantee compatibility with undocumented Claude internals.

## Core principles

### Evidence before persistence

A lesson must reference an observable correction, verified successful method, or explicit user request. Plausible model inference alone may create a review note but cannot authorize a durable fact.

### Correct destination

- Stable personal or environment fact → memory.
- Persistent project convention → project `CLAUDE.md` or scoped rule.
- Reusable multi-step procedure → skill.
- Deterministic lifecycle or safety requirement → hook proposal.
- Detailed supporting material → skill reference.
- Temporary task state or completed-work log → discard.

### Search before create or patch

The reviewer searches existing memories, rules, and skills first. It prefers, in order:

1. patch the exact owning artifact;
2. expand an existing umbrella artifact;
3. add a reference to an existing skill; then
4. propose a new artifact.

### Recoverable by construction

A write is not successful until its journal is prepared, recovery material is durable, filesystem installation is synced, validation passes, and observed hashes are recorded. SQLite and filesystem updates are not one atomic transaction; nonterminal journal records are reconciled from actual filesystem state.

### Deterministic authorization

An LLM may propose a classification or patch. Code decides whether the target, scope, ownership, content class, and mutation mode are allowed.

## Knowledge taxonomy

| Class | Examples | Destination | Initial authorization |
| --- | --- | --- | --- |
| User fact | shell preference, stable tool choice | user memory or user `CLAUDE.md` | Review |
| Project fact | build command, repository layout | project memory | Review |
| Project instruction | test gate, naming convention | project `CLAUDE.md` or rule | Review |
| Procedure | migration/debugging workflow | personal or project skill | Review |
| Enforcement | block secret reads, run formatter | hook | Proposal only in Phase 1 |
| Supporting detail | API reference, long troubleshooting notes | skill `references/` | Review |
| Temporary state | current TODO, one completed operation | none | Discard |
| Volatile identifier | commit SHA, PR number, run ID | none | Discard |
| Unverified inference | guessed cause or preference | candidate only | Never auto-persist |
| Sensitive content | credentials, tokens, private transcript | none | Redact and reject |

## Lean architecture

```mermaid
flowchart LR
    S[Claude Code CLI] --> L[Explicit learn skill]
    L --> C[Bounded proposal context]
    C --> R[Reviewer skill / agent]
    R --> P[Untrusted typed proposal submission]
    P --> A[Policy and authorization]
    A -->|approved| M[Journaled mutation engine]
    A -->|needs review| U[User review]
    U -->|approve| M
    U -->|reject| X[Rejected proposal]
    M --> J[(Journal and recovery data)]
    M --> K[New personal skill]
    H[Optional later hooks] -.-> C
```

### Process boundaries

- Claude Code owns the session, model calls, plugin loading, tool execution, and hook invocation.
- The plugin owns skills, agents, hook declarations, and wrappers.
- `claude-si` owns candidate/proposal metadata, deterministic policy, journaled installation, recovery, and rollback.
- Claude's knowledge files remain the authoritative content Claude consumes.
- The state database is authoritative only for candidates, provenance, lifecycle metadata, and mutation history.
- The user owns approval of review-gated mutations.

No continuously running daemon is required for the first three phases. Commands and later hooks run the engine as bounded local processes. SQLite transactions protect metadata only; the mutation journal reconciles metadata with filesystem reality.

## Proposed implementation technology

Use a small Go command-line engine compiled as a native executable, plus Markdown/JSON plugin assets.

Reasons:

- one native executable for hook startup;
- no dependency on macOS system Python or a user-visible Node installation;
- straightforward cross-compilation for later Linux devcontainers;
- standard-library support for hashing, JSON, filesystem safety, and process control; and
- a narrow CLI/JSON contract that is testable without Claude.

SQLite shall be embedded through a maintained driver, with WAL enabled only after concurrency and recovery tests prove cleanup behavior. Replacing SQLite requires a design amendment; this specification does not promise interchangeable storage implementations.

The plugin shall invoke the executable through a wrapper resolved from `${CLAUDE_PLUGIN_ROOT}`. Distribution shall package the correct macOS architecture artifact and verify its checksum. Source-tree execution is not accepted as the release smoke test.

## Proposed repository structure

```text
.
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   └── learning-reviewer.md
├── hooks/
│   └── hooks.json
├── skills/
│   ├── self-improvement/
│   │   ├── SKILL.md
│   │   └── references/learning-policy.md
│   ├── review-learning/SKILL.md
│   ├── curate-learning/SKILL.md
│   └── rollback-learning/SKILL.md
├── bin/
│   └── claude-si-hook
├── cmd/
│   └── claude-si/main.go
├── internal/
│   ├── artifact/
│   ├── candidate/
│   ├── classify/
│   ├── policy/
│   ├── redact/
│   ├── state/
│   └── mutation/
├── tests/
│   ├── fixtures/hooks/
│   └── integration/
└── docs/specs/
```

Only `plugin.json` belongs inside `.claude-plugin/`; components remain at plugin root as required by Claude Code's plugin layout.

## Component design

### Plugin hook (`v0.1.1` and later)

The hook is a thin adapter. It:

1. reads one Claude hook event from stdin;
2. invokes `claude-si candidate capture` with bounded execution time;
3. emits no candidate body to the Claude conversation;
4. exits successfully even when capture fails; and
5. records local diagnostics without leaking transcript content.

The hook does not perform LLM review or mutate knowledge.

### Deterministic detector

The detector is not part of `v0.1`. Beginning in `v0.1.1`, it computes signals primarily from minimal `PostToolUse` and `PostToolUseFailure` envelopes. `Stop` closes the turn but does not assume `transcript_path` is synchronously complete. Bounded transcript reading is an optional compatibility fallback with explicit retry and byte/message limits.

Signals include:

- explicit user correction language;
- failed tool/command followed by verified success;
- skill use followed by workaround or correction;
- explicit remember/reuse request;
- task complexity threshold; and
- duplicate candidate fingerprint.

The detector outputs a normalized candidate envelope or no-op. It does not decide the final destination.

### Reviewer

The reviewer is a Claude plugin agent or skill. The engine does not invoke a model or private Claude API. The learning skill calls `claude-si proposal context <id> --json`; the reviewer reasons over that bounded context and submits untrusted typed JSON through `claude-si proposal submit --stdin`.

It must return a typed proposal:

```json
{
  "candidate_id": "...",
  "classification": "skill",
  "scope": "user",
  "target": "~/.claude/skills/generated-unique-name/",
  "action": "create_personal_skill",
  "lesson": "...",
  "evidence": [{"kind": "verified_success", "ref": "..."}],
  "confidence": 0.0,
  "risk_flags": [],
  "ownership": "human-owned-after-creation",
  "files": {"SKILL.md": "..."}
}
```

The engine validates this schema and independently checks target, scope, ownership, uniqueness, containment, and forbidden content. No undocumented structured callback is assumed.

### Artifact discovery

Phase 1 discovery searches supported personal knowledge roots read-only for duplicate review. Later project support uses an engine-owned authorization registry containing canonical repository identity/root, explicit user enrollment, permitted destination classes, expiry, and revocation. Trust is never inferred from `cwd`, plugin enablement, or Claude UI state.

It must defend against:

- path traversal;
- symlink escape;
- case-normalization surprises;
- project root changes;
- stale indexes; and
- files changing between proposal and apply.

Search results are advisory. The current file is always re-read before mutation.

### Policy engine

The policy engine is the only component that returns an authorization result:

- `discard`;
- `candidate_only`;
- `needs_review`;
- `allowed_after_approval`; or
- `allowed_automatic` beginning in Phase 2.

Policy decisions include stable machine-readable reason codes. The plugin cannot bypass policy by changing prose.

### Mutation engine

The mutation engine accepts a typed, authorized proposal. It owns an explicit mutation journal, recovery data, filesystem installation, observed-hash validation, provenance, reconciliation, and rollback-as-a-new-mutation. It does not claim an atomic transaction across SQLite and the filesystem.

It does not accept arbitrary shell commands. `v0.1` supports only creation of one new uniquely named personal skill directory. Existing-file replacement is deferred to Phase 2A.

### State store

Logical entities:

- `candidates` — normalized lesson opportunities and status;
- `evidence_refs` — minimal references and fingerprints;
- `proposals` — typed classification and diff against a base hash;
- `artifacts` — indexed Claude knowledge and ownership;
- `mutations` — intended/observed hashes, recovery path, actor, journal state, and outcome;
- `activity_events` — Phase 3 engine-owned metadata only;
- `curation_proposals` — Phase 3 consolidation/archive proposals; and
- `settings` — engine policy, never Claude credentials.

Candidate states:

```text
captured -> reviewing -> needs_review -> approved -> applying -> applied
    |           |             |             |           |
    +--------> discarded <----+----------> rejected     +--> failed
```

Metadata transitions are transactional and idempotent. Filesystem transitions are reconciled through the mutation journal. Replaying the same hook event cannot create duplicate candidates.

## Storage layout

Default local root on macOS:

```text
~/Library/Application Support/claude-self-improvement/
├── state.sqlite
├── recovery/<random-mutation-id>/
├── archive/
├── logs/
└── locks/
```

The engine shall use the operating system's user data directory on future platforms rather than assuming the macOS path. Configuration may override this root for tests. Runtime state never lives inside the plugin cache because plugin updates may replace that directory.

Recovery content inherits the sensitivity of the artifact. User-only permissions, parent containment, and symlink checks are required before creation. Recovery names are random mutation IDs, not content hashes; content is never deduplicated across projects or scopes. Credential canaries are rejected before a recovery copy or staged artifact is written. Successful mutation recovery data is retained for 30 days by default and removed only through a symlink-safe explicit purge. Recovery data must not be uploaded, synchronized, or committed automatically.

## Privacy and sensitive-data policy

### Never persist

- Claude, Anthropic, GitHub, or MCP credentials;
- `.env` values;
- complete transcript bodies;
- complete user prompts or assistant responses;
- private file contents unrelated to the learned artifact;
- authentication caches;
- account identifiers; or
- shell environment dumps.

### Minimal evidence

Persist only:

- session/event opaque identifier;
- timestamp;
- evidence kind;
- redacted normalized summary;
- source surface class;
- content fingerprint; and
- verification outcome.

Review may read bounded original evidence locally on demand. If unavailable, the candidate remains unverified rather than promoting the stored summary to fact.

### Redaction

Redaction runs before persistence and again before logs or diagnostics. Credential-shaped data causes rejection when safe redaction would destroy the meaning of the candidate.

## Concurrency and consistency

Multiple Claude surfaces and external editors may run simultaneously. Therefore:

- candidate capture uses database transactions and unique event fingerprints;
- mutation uses one exclusive cross-process lock that coordinates only cooperating `claude-si` processes;
- proposals include a base content hash;
- apply rechecks canonical path and hash;
- stale proposals return to review;
- recovery data and staged files are `fsync`ed before rename;
- the final parent directory is `fsync`ed after rename;
- post-write validation occurs before success is recorded; and
- nonterminal journal entries are reconciled from actual filesystem hashes before another mutation.

The design does not rely on an in-memory singleton and does not claim race-free coordination with editors, Git, Claude Code, or other external writers. Existing-file support rechecks immediately before rename and treats conflict detection as best effort; it never directly mutates Claude-managed auto-memory.

## Artifact ownership

Ownership values:

- **human:** created or explicitly claimed by the user;
- **agent:** created by this system with valid provenance and explicitly opted into agent management;
- **mixed:** agent-created but externally modified, or jointly maintained;
- **unknown:** no reliable provenance.

Phase 1 requires review for all mutations and defaults new artifacts to `human`. Phase 2B may automatically patch only unchanged `agent` artifacts under its eligibility policy. `human`, `mixed`, and `unknown` remain review-gated.

## Validation

Validators shall cover:

- UTF-8 and size limits;
- Markdown/frontmatter syntax;
- skill required fields and directory naming;
- relative reference existence;
- duplicate skill names and trigger collisions;
- forbidden executable or settings changes;
- path containment;
- policy-specific content rules; and
- plugin schema through the official Claude validator where available.

Validation warnings block automatic mutation.

## Commands and surface UX

The native engine exposes stable JSON output. Plugin skills provide natural-language UX.

Initial user-facing operations:

- status and health;
- list/show candidates;
- review and generate a proposal;
- approve/apply or reject;
- inspect mutation history; and
- rollback.

Phase 3 adds curator scan, proposal, archive, and restore.

Claude-generated prose is not parsed to determine whether an operation succeeded; the wrapper checks process exit status and JSON result fields.

## Failure model

| Failure | Required behavior |
| --- | --- |
| Hook timeout or crash (`v0.1.1+`) | Do not block Claude; record local diagnostic |
| Store unavailable | Disable capture/mutation; preserve Claude operation |
| Reviewer unavailable | Keep candidate queued |
| Invalid proposal | Reject with reasons; no write |
| Stale target | Return to review; no force apply |
| Recovery preparation failure | Abort before filesystem installation |
| Write interruption | Leave a reconcilable journal state; never infer success from SQLite alone |
| Installed hash matches intent but journal is nonterminal | Validate and complete the journal during recovery |
| Installed path has unexpected bytes | Mark conflict; do not overwrite or auto-restore |
| Post-write validation failure | Journal failure and perform a separate recovery mutation where safe |
| Rollback collision | Require review; rollback is a new mutation and never overwrites current content |
| Unknown Claude version/schema | Fail closed for capture or mutation feature, not Claude itself |

## Version compatibility

The project shall maintain fixtures for each supported Claude Code hook schema and a small compatibility layer at the plugin boundary.

A new Claude Code version is supported only after:

1. plugin load verification from the exact release artifact;
2. strict validator output with no unexpected warnings;
3. hook fixture capture and schema comparison for releases that enable hooks;
4. smoke tests for each surface actually certified by that release; and
5. recovery and rollback verification.

Unsupported versions may run with self-improvement disabled and a diagnostic. They must not receive guessed writes.

## Distribution

Initial distribution is private:

- source hosted in `plume-works/claude-self-improvement`;
- packaged plugin installed at user scope;
- native macOS artifact built by CI for supported architecture(s);
- checksums published with each private release; and
- plugin version and engine version reported by `claude-si doctor`.

A private Claude plugin marketplace may be added after local package installation is proven. Public distribution and marketplace submission are non-goals until the security model and privacy review are complete.

## Phase boundaries

| Concern | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
| --- | --- | --- | --- | --- |
| Candidate detection | Explicit in `v0.1`; hooks in `v0.1.1` | Harden | Engine-owned events only | Adapt per environment |
| Proposed change | One new skill in `v0.1` | Existing-artifact patches | Consolidation proposals | Contract-specific |
| User approval | Every mutation | Every Phase 2A mutation; risk/ownership dependent in 2B | Semantic curation | Environment dependent |
| Automatic writes | None | Phase 2B narrow agent-owned patches | Metadata only | No broader by default |
| Archive | No | No | Reversible | Synchronization-aware |
| Local surfaces | CLI `v0.1`; VS Code `v0.1.2`; Desktop `v0.1.3` | Previously certified surfaces | Previously certified surfaces | Adapter-specific |
| Devcontainer/SSH | No | No | No | Independent adapters |
| Desktop Chat/Cowork | No | No | No | Public-seam-dependent |

## Architecture risks

### Hook noise and cost

A model call after every `Stop` event would be expensive and intrusive. The deterministic detector must suppress ordinary turns before review.

### Prompt-based authorization

Claude may produce a convincing but unsafe proposal. Typed engine policy, not prose, owns authorization.

### Configuration corruption

Simultaneous surfaces and editors can race. Engine locks coordinate only engine processes. Journaled recovery, immediate pre-rename checks, observed-hash validation, conflict handling, and packaged crash tests are release blockers; race-free external compare-and-swap is not claimed.

### Knowledge pollution

Over-capture can make Claude worse. The taxonomy, discard rules, review-only first phase, and later engine-event curation protect quality.

### Surface topology confusion

Desktop Local, cloud/Cowork, SSH, and devcontainers do not share one filesystem. Phase 4 treats each as a separate adapter rather than pretending configuration synchronization is automatic.

### Plugin update and runtime mismatch

The plugin and engine may update independently. Every invocation performs a protocol-version handshake. Incompatible versions disable mutation and report exact remediation.

## Decision log

1. **Plugin plus native engine, not prompt-only:** deterministic state, policy, journaling, recovery, and rollback require code.
2. **No daemon for initial releases:** bounded hook/command processes reduce lifecycle and security surface.
3. **Explicit, review-only CLI tracer bullet first:** quality and safety evidence precede hooks, additional surfaces, existing-file edits, and unattended writes.
4. **Claude files remain authoritative:** the engine does not replace Claude memory or skills with a private database.
5. **Go proposed for engine:** native startup and later cross-compilation outweigh a larger initial build step.
6. **No full transcript telemetry:** minimal evidence is sufficient and materially reduces privacy risk.
7. **Additional surfaces and environments are independent gates:** CLI value cannot be held hostage by desktop, cloud, or container topology.
8. **Filesystem and SQLite are reconciled, not atomic together:** mutation journals and observed hashes define recovery.

## Open implementation questions

These must be resolved during Phase 1 seam verification, not guessed:

1. Exact minimum Claude Code version exposing the plugin/skill features required by `v0.1`.
2. Stable hook fields available for `v0.1.1` deduplication and bounded evidence lookup.
3. Packaged plugin behavior in each incrementally certified surface.
4. Whether Desktop Local exposes the packaged executable consistently.
5. Packaging format for Intel and Apple Silicon Macs.
6. Exact auto-memory discovery contract safe for supported versions. Direct external writes remain disabled unless Anthropic documents a supported resolver and mutation seam.

Each answer must be captured in tests and, where it changes this design, in a specification amendment.

## Acceptance of this design

Spec-0001 is ready for implementation only when maintainers accept:

- the review-only `v0.1` boundary;
- the ownership and privacy model;
- the supported-surface matrix;
- the proposed engine/plugin split;
- the mutation and rollback invariants; and
- the explicit deferral of cloud, Chat, SSH, and devcontainer support.
