# Spec-0001: Hook-driven experiential learning plugin MVP

- **Status:** Accepted; **fully implemented**. Slices 1–4 are complete, the offline suite passes, and the packaged smoke test passes against a real Claude Code session. The section 15 acceptance gate is met.
- **Scope:** Standalone Claude Code CLI on one local user account
- **Runtime:** Python 3.9+, standard library only
- **Implementation strategy:** package a narrowed `claude-improve` reviewer as a Claude Code plugin and invoke it selectively through supported lifecycle hooks
- **Supersedes for MVP planning:** the earlier multi-phase specifications, retained as [hypothetical extensions](../hypothetical-extensions/specs/README.md)

## 1. Product goal

Claude should learn from completed work in the same practical sense that Hermes does:

> recognize a verified correction or hard-won workflow, extract the reusable lesson, route it to the right durable artifact, and make that lesson available in later sessions.

The user must not have to design test procedures, maintain evaluation datasets, or remember to invoke reflection after every useful experience. Automatic reflection is allowed; durable mutation remains explicitly authorized by the user.

Ordinary learning is grounded by direct evidence such as:

- an explicit user correction;
- a failed command or approach followed by a verified successful one;
- a reusable workflow that produced the requested result;
- repeated friction in the current session;
- explicit confirmation that a non-obvious technique worked; or
- a direct request to remember an approach.

## 2. Proven platform seam

Claude Code plugins can package hooks, skills, and scripts. The supported [`Stop`](https://code.claude.com/docs/en/hooks#stop) event runs after the main agent finishes responding and provides the session identifier, transcript path, final assistant response, continuation state, and outstanding background work.

Command hooks support [`asyncRewake`](https://code.claude.com/docs/en/hooks#command-hook-fields): the hook runs without delaying the completed response and can wake the idle Claude session when a background review finds something actionable.

Anthropic's official [`security-guidance`](https://code.claude.com/docs/en/security-guidance#how-the-plugin-integrates-with-claude-code) plugin proves the required architecture in production:

```text
UserPromptSubmit captures a baseline
        |
        v
Stop launches an independent background model review
        |
        v
findings wake the original session
        |
        v
Claude acts on the findings in a follow-up turn
```

This MVP substitutes experiential-learning review for security review. It does not depend on private IDE integration or a daemon.

## 3. User experience

### 3.1 Automatic path

```text
user and Claude complete useful work
        |
        v
hooks record bounded high-signal events
        |
        v
Stop allows the completed response to return immediately
        |
        v
cheap deterministic gate decides whether reflection is warranted
        |
        +---- no signal ----> delete ephemeral turn data; stay silent
        |
        v
independent background reviewer analyzes the bounded evidence
        |
        +---- no durable lesson ----> stay silent
        |
        v
wake the original session with one structured candidate
        |
        v
search existing instructions, rules, and skills for the owner
        |
        v
show one exact proposed patch or new skill
        |
        v
user explicitly applies or rejects it
        |
        v
backup, apply, verify, and expose rollback
```

The primary task is complete before review begins. Review failure, timeout, cancellation, or rejection must not invalidate completed work.

### 3.2 Manual path

The plugin also exposes:

```text
/self-improve:improve [optional focus]
```

This forces the same bounded reviewer pipeline when automatic detection misses a meaningful experience. It is not a separate mutation path.

### 3.3 Approval path

A candidate is inert until the user enters an explicit command containing its identity and displayed hash prefix:

```text
/self-improve:apply <proposal-id> <hash-prefix>
/self-improve:reject <proposal-id>
/self-improve:rollback <mutation-id>
```

`apply` consumes a one-time authorization record derived from that literal user prompt. A model-generated tool call, generic “looks good,” or approval of a summary does not authorize mutation.

## 4. Plugin package

The first packaged artifact has this conceptual layout:

```text
claude-self-improvement/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json
├── skills/
│   ├── improve/SKILL.md
│   ├── apply/SKILL.md
│   ├── reject/SKILL.md
│   └── rollback/SKILL.md
├── scripts/
│   ├── capture-event
│   ├── review-turn
│   ├── authorize-proposal
│   ├── apply-proposal
│   └── rollback-mutation
└── reviewer/
    ├── prompt.md
    └── schema.json
```

Names may change during implementation, but the separation of capture, review, authorization, mutation, and rollback is normative.

### 4.1 Implementation decisions

#### Runtime and dependencies

Runtime code under the plugin directory must import successfully with nothing but a system `python3`, offline. Hook scripts run inside Claude Code's environment rather than one the plugin controls, capture hooks run on a five-second budget, and every capture path must fail open. A third-party import in that path requires a bootstrap step in precisely the code that must be most reliable.

Anthropic's `security-guidance` plugin demonstrates the cost of the alternative: it builds a virtual environment under `~/.claude/security/`, requires `pip` and network access, documents degraded fallbacks for when that install fails, and treats YAML support as best-effort because the plugin does not install PyYAML for the user.

The rule therefore splits by location rather than by preference:

- plugin runtime code: standard library only, enforced by a test that walks the AST of every runtime module and fails on any non-stdlib import;
- tests and development tooling: unconstrained, managed with `uv`, with `project.dependencies` permanently empty.

The standard library covers hashing, JSON, unified diffs, subprocess timeouts, advisory locking, and atomic replacement. What remains hand-written is a small set of generic helpers — atomic write with fsync and mode preservation, a lock context manager, a `name`/`description`-only frontmatter reader, and a flat reviewer-output validator — alongside domain logic that no dependency provides.

#### Entry point

A single dispatcher, `scripts/si <subcommand>`, is the only executable. Hooks and skills both invoke it, so there is one place that parses hook JSON from standard input and one place that fails open. The normative separation of capture, review, authorization, mutation, and rollback required by section 4 is realized as separate modules rather than separate executables.

#### State root

Runtime state resolves in this order:

1. `${SELF_IMPROVE_STATE_DIR}`;
2. `${CLAUDE_PLUGIN_DATA}`; then
3. `~/.claude/self-improvement/`.

The explicit override precedes the plugin data directory because Claude Code sets `CLAUDE_PLUGIN_DATA` in every hook environment it creates, discarding any inherited value. An override that lost to it would have no effect on the hooks that write state, which is the only place the setting matters.

#### Environment variables

| Variable | Purpose |
| --- | --- |
| `SELF_IMPROVE_REVIEW_MODEL` | Reviewer model; defaults to `sonnet` |
| `SELF_IMPROVE_REVIEW_TIMEOUT` | Seconds to wait for the reviewer before giving up silently |
| `SELF_IMPROVE_DISABLE` | Set to `1` to disable the plugin without uninstalling it |
| `SELF_IMPROVE_REVIEWER` | Set to `1` in the reviewer's own environment; suppresses reflection in reviewer-originated sessions |
| `SELF_IMPROVE_REVIEWER_CMD` | Overrides the reviewer binary; used by tests to substitute a deterministic fake |
| `SELF_IMPROVE_STATE_DIR` | Overrides the state root |

## 5. Hook design

### 5.1 `UserPromptSubmit`

A synchronous, bounded command hook:

1. records the session and prompt identifiers;
2. detects explicit correction and retention-request markers;
3. places the current prompt in a mode-`0600` ephemeral turn file only when a review signal requires it.

It must not append raw prompts to telemetry or a durable learning database.

### 5.2 `UserPromptExpansion`

A synchronous hook records direct user invocation of the plugin's `apply`, `reject`, and `rollback` commands together with the exact `command_args`. Claude Code documents this event specifically for user-typed commands before their prompts reach Claude. The resulting one-time authorization is bound to the session, operation, proposal or mutation ID, and displayed hash prefix.

This closes the direct-command path that a `PreToolUse` hook cannot observe. Invocation by Claude through the `Skill` tool does not authorize mutation; only a matching `UserPromptExpansion` event with `expansion_type: "slash_command"` and the plugin as `command_source` is accepted.

The hook registers a wildcard matcher and performs command selection inside the script, rather than relying on a matcher expression. The namespaced form Claude Code reports in `command_name` for a plugin skill is not guaranteed, and a matcher that failed to match would silently discard the user's authorization rather than fail loudly. The script accepts an event only when `expansion_type` is `slash_command`, `command_source` is the plugin, and the command name resolves to one of the three authorizing operations. Every other expansion exits without recording anything.

### 5.3 `PostToolUseFailure`

A synchronous deterministic hook records bounded failure metadata:

- tool category;
- normalized operation signature;
- error class;
- timestamp and turn identifier; and
- no raw tool output, command secrets, or environment values.

### 5.4 `PostToolUse`

A synchronous deterministic hook pairs a successful operation with a prior compatible failure. This creates a `failed_then_succeeded` signal without asking a model to infer success from an entire historical transcript.

The implementation should use narrow tool matchers and strict timeouts. Event-capture failure always fails open.

### 5.5 `Stop`

The `Stop` command hook is configured with `asyncRewake: true` and performs the main orchestration:

1. return immediately so the primary response is not delayed;
2. skip when `stop_hook_active` is true;
3. skip while relevant background work or session wakeups remain active;
4. skip reviewer-originated sessions and plugin-generated follow-up turns;
5. run the deterministic meaningful-event gate;
6. invoke the independent reviewer only when the gate passes;
7. exit silently when no durable lesson is found; or
8. wake the original session with one structured candidate when review succeeds.

The hook exits successfully for no-op and internal failure cases. It uses the documented `asyncRewake` signal only when a valid candidate should wake Claude.

### 5.6 `SessionEnd` and `SessionStart`

`SessionEnd` is not the primary reviewer. It may delete expired ephemeral files or queue an already-detected candidate for the next session, but it must not depend on having time to perform model review or interactive approval after the session has terminated. The implementation restricts it to an expiry sweep.

`SessionStart` performs the retrieval half that section 11 requires: when review completed while no session was available to wake, it reports the retained candidates as context so the user can ask for them explicitly. It performs no model review and no mutation.

## 6. Meaningful-event gate

The gate is deterministic and cheap. It requests model review only when at least one supported signal exists:

1. **explicit retention:** “remember this,” “always do this,” or equivalent direct intent;
2. **explicit correction:** the user replaces a prior assumption, command, format, or workflow;
3. **verified workaround:** a compatible failed operation is followed by success;
4. **repeated friction:** the same normalized operation fails or is retried beyond a configured threshold;
5. **confirmed technique:** the user explicitly confirms that a non-obvious approach solved the task;
6. **reusable completion:** the final response identifies a completed multi-step procedure with verified outputs; or
7. **manual force:** `/self-improve:improve` was invoked.

A signal is permission to reflect, not proof that a durable lesson exists. The reviewer may and often should return no candidate.

The MVP enforces:

- no more than one reviewer invocation per completed user turn;
- no more than one candidate returned per review;
- cooldown and daily invocation limits;
- proposal fingerprint deduplication; and
- recursion guards for reviewer and plugin-generated sessions.

## 7. Independent reviewer

### 7.1 Relationship to `claude-improve`

[`TerenceBristol/claude-improve`](../case-study/claude-improve/README.md) supplies the reasoning baseline:

- analyze corrections, friction, successful techniques, and capability gaps;
- distinguish project-local and user-global placement;
- search for contradictions and existing owners;
- rank findings by impact and confidence; and
- present findings individually.

The MVP does **not** execute the existing monolithic `/improve` prompt on every turn. That workflow is interactive, scans broad configuration and historical state, launches multiple agents, and can directly mutate several artifact classes.

Instead, implementation extracts a noninteractive, current-turn reviewer prompt with a strict schema and no mutation tools.

### 7.2 Reviewer input

The reviewer receives only:

- bounded event records for the current turn;
- the current user prompt when required for a detected correction or retention request;
- `last_assistant_message` from `Stop`;
- a redacted summary of verified failure-to-success transitions;
- summaries and paths of candidate instruction, rule, and skill owners; and
- accepted/rejected proposal fingerprints needed for deduplication.

It does not receive unrelated historical transcripts, credentials, environment dumps, or unrestricted filesystem access.

### 7.3 Reviewer isolation

The reviewer runs as a separate Claude call with fresh context, a reviewer-only system prompt, plugin hooks disabled, and no tools at all. It uses the user's configured Claude authentication and introduces no separate credential requirement.

The committed invocation is:

```bash
claude -p --model "${SELF_IMPROVE_REVIEW_MODEL:-sonnet}" \
  --system-prompt-file "<plugin>/reviewer/prompt.md" \
  --tools "" --disallowedTools "*" --strict-mcp-config \
  --settings '{"disableAllHooks": true}' \
  --output-format json --max-turns 1
```

The reviewer receives its entire evidence bundle on standard input. Candidate owner paths and summaries are gathered deterministically by the orchestrator and inlined, so the reviewer needs no filesystem access whatsoever. This is strictly stronger than the read-only artifact allowlist this section would otherwise permit: the reviewer has no tool with which to read, write, or execute anything.

`SELF_IMPROVE_REVIEWER=1` is set in the reviewer's environment so that any session it originates suppresses reflection.

### 7.4 Reviewer output

The reviewer returns strict structured data:

```json
{
  "decision": "discard | propose",
  "signal_type": "explicit_correction",
  "evidence_summary": "bounded, redacted summary",
  "lesson": "reusable statement",
  "applicability": "when this lesson applies",
  "counterexample": "when it should not apply",
  "destination_scope": "project | user",
  "destination_kind": "CLAUDE.md | rule | skill",
  "owner_query": "terms used to find an existing owner",
  "confidence": "high | medium | low"
}
```

Malformed output, low confidence, unsupported destinations, and policy violations become `discard`.

The reviewer does not emit final file bytes and cannot write files.

## 8. Routing and proposal construction

After a valid reviewer result, the foreground plugin flow searches the currently loaded and existing Claude instructions, rules, and skills.

Preference order:

1. patch the currently loaded owner;
2. patch an existing class-level umbrella;
3. add or patch a linked reference owned by an umbrella; or
4. propose a new skill only when no suitable owner exists.

The MVP may patch one explicitly selected artifact or create one personal/project skill. It must not perform broad configuration cleanup, delete artifacts, modify Claude-managed auto-memory, rewrite hooks/settings, or consolidate multiple files.

### 8.1 Path allowlist

A proposal may target only these paths. The list is normative and is enforced by the mutator, not by the reviewer or by any model-authored instruction.

| Scope | Allowed targets |
| --- | --- |
| User | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md`, `~/.claude/skills/<name>/SKILL.md` |
| Project | `./CLAUDE.md`, `./.claude/CLAUDE.md`, `./.claude/rules/*.md`, `./.claude/skills/<name>/SKILL.md` |

Paths are resolved to their real location before the check, and containment and shape are both decided on the resolved path. Traversal outside an allowed root and non-regular files are rejected before any I/O.

Symlink rejection is scoped deliberately. A symlink for the target itself is always refused, because the indirection makes the reviewed destination and the written destination two different things, as is any symlinked component between an allowed root and the target. Components above the root are not checked: symlinked prefixes are ordinary and outside this system's concern, since macOS reaches `/tmp` and `/etc` through them and a home or checkout directory may be one too. Rejecting those would refuse most scratch directories while protecting nothing.

`AGENTS.md` is deliberately excluded, including in repositories such as this one that keep their instructions there and import them from `CLAUDE.md`. Claude Code does not load `AGENTS.md` directly, so it is not an owner this system can reason about; a lesson belonging to such a repository is routed to the importing `CLAUDE.md` or to a rule.

Everything not listed above is rejected, including `settings.json`, hook configuration, Claude-managed auto-memory, and arbitrary source files.

A proposal must contain:

- immutable proposal ID and content hash;
- destination and scope;
- target preimage hash or an explicit “new file” assertion;
- exact old and new bytes;
- evidence summary without raw transcript bodies;
- reusable lesson, applicability, and counterexample;
- why the selected artifact owns the lesson;
- backup and rollback behavior; and
- expiry time.

Proposal construction may use Claude, but the deterministic mutator applies only the staged bytes represented by the approved hash.

## 9. Mutation protocol

`apply-proposal` must:

1. consume a matching, unexpired, one-time authorization record;
2. validate proposal ID and full content hash against the displayed hash prefix;
3. resolve the target under an allowed Claude project or user configuration root;
4. reject symlinks, traversal, unexpected file types, and out-of-scope paths;
5. re-read the target and require its current hash to match the proposal preimage;
6. create a mode-preserving recoverable backup and fsync it;
7. atomically install exactly the approved bytes;
8. re-read and verify the installed hash;
9. append a redacted mutation record; and
10. invalidate the proposal and authorization token.

On any pre-install failure, the target remains unchanged. On interrupted or ambiguous installation, the next command reconciles observed hashes before allowing another mutation.

`rollback-mutation` performs the same path, symlink, preimage, atomic-write, and verification checks in reverse. It never overwrites a target that has changed independently since the mutation.

## 10. State and privacy

Runtime state is private to the user and separated into:

- ephemeral per-turn input, deleted after review or expiry;
- staged immutable proposals;
- one-time authorization records;
- verified mutation backups; and
- redacted diagnostics and proposal fingerprints.

### 10.1 State layout

Relative to the state root defined in section 4.1. Directories are created mode `0700` and files mode `0600`.

| Path | Contents | Lifetime |
| --- | --- | --- |
| `turns/<session>/<turn>.json` | bounded event records for one turn | deleted after review; expires after 1 hour |
| `candidates/<id>.json` | accepted reviewer output awaiting presentation | expires after 24 hours |
| `proposals/<id>.json` | immutable staged bytes and hashes | expires after 24 hours |
| `authorizations/<nonce>.json` | one-time apply, reject, or rollback grant | expires after 10 minutes |
| `backups/<mutation_id>/` | mode-preserving verified preimage | retained |
| `inflight.json` | interrupted-mutation reconciliation marker | cleared on completion |
| `mutations.jsonl` | redacted mutation and rollback journal | retained |
| `fingerprints.json` | accepted and rejected proposal fingerprints | retained |
| `counters.json` | cooldown and daily invocation counters | retained |
| `pending.json` | candidates awaiting an available session | expires with the candidate |
| `diagnostics.jsonl` | redacted error classes only | retained |

Permissions default to user-only access. Durable state must not contain:

- raw prompts or assistant responses;
- transcript bodies;
- credentials, tokens, cookies, or environment values;
- raw tool output;
- full shell commands containing arguments; or
- unrelated project file content.

The plugin never edits or parses Claude-managed auto-memory internals.

## 11. Failure behavior

- Capture/gating failure: fail open and preserve the completed task.
- Reviewer timeout, authentication failure, or malformed output: stay silent and record only a redacted error class.
- Reviewer unavailability distinct from reviewer disagreement: the recorded class must name a provider failure — rate limit, overload, usage limit, unreachable model, or other API error — separately from a review that ran and proposed nothing. Both stay silent; only the class distinguishes a transient condition from a decision, and the class is all a later investigation has.
- Session unavailable when review completes: retain the staged candidate for explicit retrieval on the next session start; do not mutate.
- Duplicate candidate: suppress it.
- User rejection: invalidate the candidate and retain only its fingerprint and rejection reason category.
- Stale target or conflicting edit: refuse application and require regeneration.
- Backup or verification failure: do not claim success; reconcile or offer verified rollback.

## 12. Explicit non-goals

The MVP does **not** include:

- SkillOpt, GEPA, or another prompt optimizer;
- user-authored train/validation/test datasets;
- model-generated rubrics treated as proof of improvement;
- full `/improve` scans on every turn;
- broad or unattended historical transcript harvesting;
- automatic adoption of model-authored changes;
- autonomous edits to Claude-managed auto-memory;
- multi-artifact restructuring, deletion, or semantic consolidation;
- long-term usage scoring or stale-skill curation;
- VS Code, Desktop, SSH, devcontainer, cloud, or multi-user certification; or
- daemon, federation, vector-memory, distributed-training, or model-weight infrastructure.

These remain hypothetical extensions rather than MVP dependencies.

## 13. Implementation sequence

### Slice 1: packaged manual tracer bullet

- Package the plugin and `/self-improve:improve` command.
- Run the isolated reviewer against a redacted fixture/current-turn bundle.
- Stage one exact proposal.
- Exercise explicit authorization, atomic application, fresh-session discovery, and rollback.

### Slice 2: deterministic event capture

- Add `UserPromptSubmit`, `PostToolUseFailure`, and `PostToolUse` capture.
- Implement event schemas, redaction, expiry, deduplication, and meaningful-event unit tests.
- Keep automatic model invocation disabled.

### Slice 3: automatic asynchronous review

- Add the guarded `Stop` hook with `asyncRewake`.
- Invoke the independent reviewer only when the deterministic gate passes.
- Wake the original session only for a valid, non-duplicate candidate.

### Slice 4: packaged acceptance

- Install the built plugin into a clean test Claude home.
- Exercise correction, failure-to-success, no-signal, rejection, approval, stale-target, restart, and rollback scenarios.
- Verify that a fresh Claude Code CLI session discovers the resulting instruction or skill.

## 14. Required tests

### Deterministic tests

- event normalization and correction/retention detection;
- failed-then-succeeded pairing;
- no-signal suppression and cooldown limits;
- reviewer recursion and `stop_hook_active` guards;
- schema rejection and candidate deduplication;
- path allowlist, traversal, symlink, stale-hash, and expiry rejection;
- exact authorization consumption;
- backup, atomic installation, verification, interrupted-state reconciliation, and rollback; and
- redaction and ephemeral-data deletion.

### Integration tests

- hook JSON fixtures for every supported event;
- fake reviewer returning discard, valid candidate, malformed output, timeout, and failure;
- asynchronous wake only for a valid candidate;
- session-unavailable candidate retrieval;
- proposal presentation and literal user authorization; and
- fresh process/session discovery of an applied artifact.

### Real packaged smoke test

This test requires an interactive Claude Code session and is therefore a documented manual procedure in [`docs/smoke-test.md`](../smoke-test.md) rather than part of the automated suite. At least one supported Claude Code CLI version must demonstrate:

1. a completed task with a verified correction returns its normal response without waiting for review;
2. the asynchronous reviewer wakes the same idle session with one candidate;
3. the user sees the exact destination and bytes;
4. rejection leaves the target unchanged;
5. literal apply authorization installs exactly the displayed bytes;
6. a fresh session discovers the resulting instruction or skill; and
7. rollback restores the verified preimage.

No user-authored skill test procedure or optimization benchmark is required.

## 15. MVP acceptance gate

The MVP is complete only when one packaged local workflow passes the real smoke test and proves:

1. automatic reflection occurs only after meaningful supported signals;
2. no-lesson turns remain silent and produce no durable proposal;
3. the reviewer is independent and cannot mutate artifacts;
4. routing searches existing owners before proposing creation;
5. user authorization is bound to one exact immutable proposal;
6. approval applies only reviewed bytes to one permitted artifact;
7. interruption, stale edits, and path attacks fail without overwriting unexpected content;
8. fresh-session discovery succeeds;
9. verified rollback succeeds; and
10. persisted state and diagnostics contain no raw transcript, credential, prompt, assistant-response, or tool-output body.

The product claim is narrow: Claude can autonomously notice a meaningful experience and propose retaining its verified reusable lesson safely. It does not claim that every retained lesson statistically improves every future behavior.
