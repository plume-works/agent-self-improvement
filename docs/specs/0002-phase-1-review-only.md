# Spec-0002: Phase 1 — Review-only local core

- **Status:** Proposed
- **Date:** 2026-07-28
- **Depends on:** [Spec-0001](0001-initial-system-design.md)
- **Initial supported topology:** macOS standalone Claude Code CLI

## Summary

Phase 1 is delivered as four independently gated increments. The first release proves one narrow learning path before automatic detection or additional surfaces are allowed onto the release path.

### Release sequence

| Release | Increment | New release proof |
| --- | --- | --- |
| `v0.1` | Explicit CLI tracer bullet | One new system-owned personal skill, approved, installed, loaded, and rolled back |
| `v0.1.1` | Automatic candidate capture | Real packaged hooks capture bounded evidence without transcript dependence |
| `v0.1.2` | VS Code Local certification | The packaged user-scope plugin and engine pass the same core flow in VS Code |
| `v0.1.3` | Desktop Code Local certification | The packaged user-scope plugin and engine pass the same core flow in Desktop Local |

No later increment can redefine an earlier release as incomplete.

## `v0.1`: explicit CLI tracer bullet

### First releasable vertical slice

> In the standalone Claude Code CLI, the user explicitly invokes the learning workflow; Claude proposes one new uniquely named personal skill; the user approves it; `claude-si` installs it with journaled recovery metadata; and a fresh packaged CLI session deterministically lists and invokes the skill.

This release does not use lifecycle hooks, parse transcripts, edit existing files, write auto-memory, or certify VS Code/Desktop.

### User-visible result

The user can:

1. invoke `/self-improvement:learn` for the current lesson;
2. inspect bounded proposal context;
3. see the proposed skill name, content, evidence, ownership, and exact staged files;
4. approve or reject the proposal;
5. install one new personal skill; and
6. recover or roll back the installation.

### Plugin package

The packaged plugin contains:

- `.claude-plugin/plugin.json`;
- `/self-improvement:learn`;
- `/self-improvement:status`;
- `/self-improvement:rollback`;
- a knowledge-read-only reviewer agent or skill; and
- an executable wrapper resolving the packaged engine through `${CLAUDE_PLUGIN_ROOT}`.

“Knowledge-read-only” means the reviewer cannot directly mutate Claude knowledge. It may submit untrusted proposal JSON to engine state.

### Reviewer-to-engine protocol

Only public Claude Code seams are used. The engine never invokes private Claude APIs, reads Claude authentication state, reuses Claude credentials, or assumes an undocumented structured-return callback.

The protocol is:

```text
claude-si proposal begin --kind personal-skill --json
claude-si proposal context <candidate-id> --json
claude-si proposal submit --stdin
claude-si proposal show <proposal-id> --json
claude-si proposal reject <proposal-id> --reason <text>
claude-si proposal approve <proposal-id>
claude-si proposal apply <proposal-id>
claude-si mutation recover --json
claude-si mutation rollback <mutation-id>
claude-si status --json
claude-si doctor --json
```

1. The learning skill starts an explicit candidate.
2. The engine emits bounded context and a JSON schema.
3. The reviewer reasons in the current Claude conversation.
4. The reviewer sends typed JSON to `proposal submit --stdin` through an allowed Bash command.
5. The engine treats that JSON as untrusted input and validates it.
6. Approval and apply are separate user-gated operations.

Human-facing skills use JSON result fields and process exit status. They never scrape prose to determine success.

### Single mutable destination

`v0.1` may create exactly one new uniquely named directory beneath:

```text
~/.claude/skills/<generated-unique-name>/
```

The staged directory may contain:

- `SKILL.md`;
- `references/*.md`; and
- non-executable templates required by that skill.

It may not:

- overwrite or patch an existing path;
- create symlinks;
- add executable files or shell hooks;
- edit `CLAUDE.md`, rules, settings, agents, MCP configuration, or auto-memory;
- write project scope; or
- create more than one skill from one proposal.

At approval, the user chooses ownership:

- `human-owned-after-creation` — default; never eligible for automatic updates; or
- `agent-managed` — records provenance but still receives no automatic updates before Phase 2B.

### Journaled installation

SQLite metadata and filesystem installation are not one atomic transaction. The engine uses a recoverable mutation journal and makes no cross-store atomicity claim.

Normative sequence:

1. Acquire the engine mutation lock. The lock coordinates only cooperating `claude-si` processes.
2. Revalidate proposal, destination containment, nonexistence, and credential canaries.
3. Create a `prepared` journal record containing mutation ID, target, staged hash, intended operation, and recovery metadata.
4. Create a randomly named mutation-scoped recovery directory with user-only permissions and `fsync` its metadata.
5. Write the complete skill into a same-parent staged directory; `fsync` every file and staged directory.
6. Recheck that the final destination still does not exist.
7. Atomically rename the staged directory into place and `fsync` the parent directory.
8. Validate the installed bytes and skill structure.
9. Mark the journal `applied` only after observed filesystem hashes match the intended result.
10. Before every new mutation and at `doctor`/startup, reconcile all nonterminal journal entries from actual filesystem state.

Recovery states include:

- `prepared` — no final artifact observed; remove safe staging remnants or resume;
- `installed_uncommitted` — final artifact matches intended hash; validate and commit metadata;
- `conflict` — final path exists with unexpected bytes; stop and require user review;
- `failed` — no automatic retry after bounded recovery attempts; and
- `applied` — terminal success.

Rollback is a new journaled mutation. It does not merely change a database status. For `v0.1` rollback removes the exact unchanged system-created skill by renaming it into the mutation recovery area and syncing the parent. If the installed skill changed after creation, rollback stops with `conflict`.

### Privacy and recovery storage

Default macOS state root:

```text
~/Library/Application Support/claude-self-improvement/
```

Requirements:

- random mutation IDs and recovery names; no raw content hashes in filenames;
- no cross-project or cross-scope content deduplication;
- user-only permissions and parent/symlink checks before creation;
- reject credential canaries before staging or recovery copies are written;
- logs contain IDs, transitions, durations, and error classes only;
- raw prompts, responses, transcripts, credentials, environment values, and account IDs are never stored;
- recovery data for a successful `v0.1` installation is retained for 30 days by default;
- explicit purge lists exactly what will be removed and never follows symlinks; and
- sensitive but noncredential skill content may exist in local recovery storage for that retention period because rollback requires it.

Negative tests seed canaries into source context, proposal JSON, staged skill, logs, SQLite fields, recovery directories, diagnostics, and crash journal output.

### `v0.1` deterministic test gate

Offline tests cover:

- proposal schema and untrusted-input validation;
- exactly-one-new-skill policy;
- destination uniqueness and containment;
- path traversal, case normalization, and symlink escape;
- ownership selection and default;
- credential-canary rejection before staging;
- journal recovery at every numbered installation boundary;
- parent-directory and file `fsync` calls through injectable filesystem fixtures;
- conflict handling for external writers;
- rollback as a new journaled mutation;
- JSON CLI contracts;
- plugin schema and Markdown links; and
- zero prompt/response/credential leakage across all persistent surfaces.

### `v0.1` packaged-artifact acceptance gate

The release is complete only when all of these are observed from the exact checksummed release artifact:

1. `claude plugin validate --strict` exits successfully with no unexpected warnings.
2. User-scope installation succeeds from the packaged artifact, not the source tree.
3. Plugin and engine complete a version/protocol handshake.
4. `${CLAUDE_PLUGIN_ROOT}` resolves the packaged executable in a real CLI session.
5. `/self-improvement:learn` creates one typed proposal without changing Claude knowledge.
6. Rejection leaves no installed skill.
7. Approval and apply install one new personal skill with an `applied` journal entry.
8. A fresh CLI session proves deterministic discovery through `/context`, `/skills`, or the current official equivalent.
9. Direct skill invocation produces a fixed expected artifact or structured effect in a bounded-cost live smoke.
10. Cancellation before approval, process termination at each journal boundary, reload, and recovery produce the specified state.
11. Rollback removes the unchanged skill; a fresh CLI session no longer discovers it.
12. Uninstall stops plugin behavior while leaving engine state available for explicit recovery/purge.
13. Persistent state, recovery files, logs, and diagnostics pass secret-canary scans.

## `v0.1.1`: automatic candidate capture

This increment adds packaged hooks only after hook fixtures are pinned for the supported Claude Code version.

### Capture design

- `PostToolUse` and `PostToolUseFailure` capture minimal redacted envelopes keyed by documented session, prompt, and tool-call identifiers where available.
- `Stop` closes or scores the turn but does not treat `transcript_path` as synchronously complete.
- Transcript parsing is an optional bounded compatibility fallback, not the primary evidence source.
- Default transcript fallback bounds must name exact byte and message limits before implementation.
- `StopFailure` and user-interrupt behavior have explicit fixtures.
- Hook failure never blocks Claude response completion.
- Automatic capture creates candidates only; all proposals and mutations remain review-only.

### Acceptance gate

The installed artifact must prove real hook invocation from the plugin cache for success, tool failure, user interrupt, `StopFailure`, reload, and uninstall. Capture must deduplicate replayed events and leak no transcript body or tool payload secrets.

## `v0.1.2`: VS Code Local certification

Depends only on packaged `v0.1` core; `v0.1.1` capture is optional for this certification.

The exact release artifact must prove:

- shared user-scope plugin visibility;
- engine executable resolution in the extension environment;
- version handshake;
- explicit proposal, rejection, apply, fresh-session discovery, conflict, recovery, and rollback; and
- no dependency on the standalone CLI process already running.

## `v0.1.3`: Desktop Code Local certification

Depends only on packaged `v0.1` core; automatic capture is optional.

The exact release artifact must prove the same core flow in Desktop Code with Environment set to Local, including executable PATH/architecture behavior, fresh-session discovery, crash recovery, uninstall, and rollback.

## Deferred from Phase 1

- edits to existing skills, `CLAUDE.md`, and rules;
- project-scoped mutations;
- direct auto-memory mutation;
- automatic application;
- curation or archival;
- Desktop Chat, Cowork/cloud, SSH, and devcontainers; and
- public marketplace publication.
