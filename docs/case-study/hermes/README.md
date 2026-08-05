# Case study: Hermes Agent self-improvement system

## Status and scope

This document records a source-grounded case study of the self-improvement system in Hermes Agent. It describes how Hermes turns conversation outcomes into durable memory and reusable skills, how the relevant instructions are assembled, and which design lessons apply to Claude Self-Improvement.

This is descriptive evidence, not a normative requirement. Requirements for this repository remain under [`../../specs/`](../../specs/README.md).

### Inspected implementation

- Repository: [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)
- Installed package version: `0.19.0`
- Inspected commit: `a41d280f95c69f67380358b305b62345934ecaf3`

File names, defaults, and behavior may change after that revision.

## Executive summary

Hermes does not retrain its model. Its self-improvement system persists operational knowledge in three principal forms:

1. **User profile** for stable facts about the user and their preferences.
2. **Memory** for durable environmental facts, conventions, and lessons.
3. **Skills** for reusable procedures, including supporting references, templates, and scripts.

The behavior is not controlled by one prompt or one file. It is a layered system consisting of:

- foreground system-prompt guidance;
- tool-schema instructions;
- an automatic background review agent;
- deterministic trigger counters;
- ownership and read-before-write guards;
- filesystem persistence;
- usage/provenance telemetry; and
- a curator that marks stale skills, archives recoverably, and can optionally consolidate overlaps.

The central design principle is:

> Memory records durable facts; skills record how to perform a class of task.

The central artifact-routing principle is:

> Patch the currently loaded or existing umbrella skill before creating another skill.

## High-level architecture

```text
Completed conversation turn
          |
          +------------------------------+
          |                              |
          v                              v
Foreground agent                  Deterministic counters
may persist directly              decide whether review is due
          |                              |
          |                              v
          |                     Background review fork
          |                     replays conversation
          |                              |
          +------------------------------+
                         |
                         v
                 Classify durable lesson
                         |
        +----------------+----------------+
        |                                 |
        v                                 v
 User/profile fact                Reusable procedure
        |                                 |
        v                                 v
 USER.md or MEMORY.md       loaded skill -> umbrella ->
                            support file -> new umbrella
                                          |
                                          v
                              ownership/read-before-write
                                      guardrails
                                          |
                                          v
                              SKILL.md / references /
                                templates / scripts
                                          |
                                          v
                                usage and provenance
                                          |
                                          v
                              optional curator lifecycle
```

The ordinary response is delivered before background review starts, so learning does not compete with the user's task for foreground model attention.

## Where the instructions live

Paths below are relative to the Hermes Agent source checkout unless otherwise noted.

| File                              | Responsibility                                                                                |
| --------------------------------- | --------------------------------------------------------------------------------------------- |
| `agent/prompt_builder.py`         | Defines foreground memory and skill guidance injected into the system prompt.                 |
| `agent/system_prompt.py`          | Assembles identity, tool-aware guidance, project context, memory, and profile information.    |
| `agent/background_review.py`      | Contains the detailed post-turn memory and skill review prompts and launches the review fork. |
| `agent/turn_finalizer.py`         | Checks review triggers and starts background review after the normal response.                |
| `agent/agent_init.py`             | Loads configured nudge intervals and initializes review counters.                             |
| `tools/memory_tool.py`            | Defines the memory tool's operational instructions and persistence interface.                 |
| `tools/skill_manager_tool.py`     | Defines skill mutation instructions and mutation guardrails.                                  |
| `tools/skill_usage.py`            | Tracks ownership, use, views, patches, state, and pinning.                                    |
| `agent/curator.py`                | Implements stale-skill and consolidation lifecycle operations.                                |
| `hermes_cli/config.py`            | Defines curator defaults and other configuration defaults.                                    |
| `$HERMES_HOME/SOUL.md`            | Optional local identity and high-level continuity policy.                                     |
| `$HERMES_HOME/memories/USER.md`   | Persisted user profile and preferences.                                                       |
| `$HERMES_HOME/memories/MEMORY.md` | Persisted stable environmental facts and conventions.                                         |
| `$HERMES_HOME/skills/**/SKILL.md` | Reusable procedural knowledge loaded into future sessions.                                    |

### Prompt assembly

`agent/system_prompt.py` builds three broad tiers:

1. **Stable:** identity, tool guidance, skill prompt, execution guidance, and platform/environment hints.
2. **Context:** caller instructions and project context such as `AGENTS.md`.
3. **Volatile:** memory snapshot, `USER.md`, external memory, and session metadata.

Memory and skill guidance are tool-aware:

- memory guidance is injected only when the memory tool is available;
- skill guidance is injected only when `skill_manage` is available.

This prevents the prompt from instructing the model to perform persistence operations it cannot execute.

## Foreground learning policy

`agent/prompt_builder.py` defines two concise policy blocks.

### Memory guidance

The memory policy instructs the agent to save:

- user preferences;
- stable environment details;
- tool quirks; and
- durable conventions.

It rejects:

- task progress;
- completed-work logs;
- temporary TODO state;
- pull-request and issue identifiers;
- commit hashes;
- transient counts; and
- facts likely to be stale within roughly a week.

It also instructs the model to write memories as declarative facts rather than self-addressed commands. Procedures belong in skills.

### Skill guidance

The foreground skill policy identifies these signals:

- a complex task involving several tool calls;
- a tricky error that was actually solved;
- a non-trivial workflow discovery; or
- an existing skill found to be stale, incomplete, or wrong.

When a loaded skill is defective, the instruction is to patch it immediately rather than allow future sessions to repeat the problem.

## Automatic background review

`agent/background_review.py` contains a substantially richer review policy than the foreground prompt.

### Review modes

Hermes can run:

- a memory-only review;
- a skill-only review; or
- a combined memory-and-skill review.

The review runs in a forked agent that receives the conversation snapshot plus a dedicated review prompt. Recursive review nudges are disabled in the fork.

### Skill-routing hierarchy

The skill-review prompt establishes this preference order:

1. **Update a currently loaded skill.** If the session loaded a relevant skill, that skill is presumed to be the most likely owner of the new lesson.
2. **Update an existing class-level umbrella.** Search the library and patch the broad existing owner.
3. **Add a support file to an existing umbrella.** Put detailed material in the appropriate package directory:
   - `references/` for provider quirks, reproductions, condensed research, or authoritative excerpts;
   - `templates/` for reusable starter artifacts;
   - `scripts/` for deterministic, rerunnable actions.
4. **Create a new class-level umbrella skill.** Do this only when no existing skill owns the class of work.

A newly added support file must also be linked from the umbrella `SKILL.md` so future agents discover it.

### Positive learning signals

The review prompt treats these as actionable:

- user corrections to style, format, workflow, or step ordering;
- frustration indicating that a repeated behavior should change;
- a verified non-trivial technique, fix, workaround, or debugging path;
- a useful tool-usage pattern; and
- missing or outdated instructions in a skill used during the session.

User corrections are treated as both memory signals and skill signals when they affect how a class of task should be performed.

### Rejected learning signals

The review prompt explicitly rejects persistence of:

- narrow one-session narratives;
- skill names based on a PR, isolated error, feature codename, or today's task;
- missing binaries and other fresh-install state;
- unconfigured credentials;
- negative claims that a tool or feature is broken;
- transient failures resolved by a retry; and
- tasks that do not establish a reusable class of work.

When setup state caused a failure, the durable lesson is the verified setup or recovery procedure—not a permanent claim that the tool does not work.

### Intentional bias toward action

The review prompt is deliberately active: it warns against treating “no update” as the default. However, it still permits `Nothing to save.` when the session produced no correction, reusable technique, or durable learning.

This combines a high-recall language-model reviewer with deterministic exclusions and mutation guardrails.

## Review triggers

The foreground instruction and the automatic review trigger are related but distinct:

- the foreground prompt says a complex task of approximately five or more tool calls is a reason to save a skill directly;
- automatic skill review is controlled by an accumulated tool-iteration counter;
- `agent/agent_init.py` defaults `skills.creation_nudge_interval` to `10`;
- memory review separately defaults `memory.nudge_interval` to `10` user turns;
- `agent/turn_finalizer.py` starts review only after a final response exists and the turn was not interrupted.

Therefore, the thresholds should not be interpreted as the definition of learning. They are scheduling heuristics. The foreground agent may persist a clear lesson before an automatic review becomes due.

## Tool-schema policy

Hermes places operational policy directly in the tool descriptions exposed to the model.

### Memory tool

`tools/memory_tool.py` tells the model:

- which facts are worth retaining;
- how to distinguish user profile from general memory;
- which transient data to skip;
- that procedures belong in skills; and
- how to batch atomic add, replace, and remove operations.

### Skill-management tool

`tools/skill_manager_tool.py` tells the model:

- when to create versus update;
- to prefer targeted patches for fixes;
- to confirm with the user before creation or deletion in ordinary interactive use;
- that good skills need triggers, exact steps, pitfalls, and verification; and
- how pinning and consolidation metadata behave.

This duplicates key policy close to the mutation boundary. Even if the higher-level prompt is compressed or overlooked, the model sees relevant constraints while selecting tool arguments.

## Mutation guardrails

The review prompt alone does not authorize unrestricted writes.

### Ownership boundaries

Background curation refuses to modify:

- hub-installed skills;
- protected bundled skills;
- externally owned skill directories; and
- manually authored skills that are not marked as agent-created.

Agent-created ownership is recorded through provenance such as `created_by: "agent"` in the usage sidecar.

### Read before write

A background review must load the exact target before mutating it:

- `skill_view(name)` before changing `SKILL.md`;
- `skill_view(name, file_path=...)` before changing a support file.

The mutation tool rejects the operation if the review fork has not read the current artifact during that review turn. This reduces blind overwrites and stale-context edits.

### Human ownership

The system distinguishes agent-created content from human- or externally-owned content. Autonomous review is intentionally narrower than interactive operations performed with user approval.

This is a critical design lesson: artifact classification and a good review prompt are insufficient without enforceable ownership checks at the write boundary.

## Persistent artifacts

A typical Hermes home contains:

```text
$HERMES_HOME/
├── SOUL.md
├── memories/
│   ├── USER.md
│   └── MEMORY.md
└── skills/
    ├── .usage.json
    ├── .archive/
    ├── .curator_backups/
    └── <category>/
        └── <skill>/
            ├── SKILL.md
            ├── references/
            ├── templates/
            └── scripts/
```

The usage sidecar can record:

- creator/provenance;
- use count;
- view count;
- last-used and last-viewed times;
- patch count and last-patched time;
- lifecycle state;
- pin status; and
- archive time.

These records support lifecycle decisions without placing mutable telemetry inside the skill itself.

## Curator lifecycle

Hermes separates per-session learning from library-wide maintenance.

At the inspected revision, default curator behavior includes:

- curator enabled;
- a seven-day run interval;
- a two-hour minimum idle period;
- stale marking after 30 days without use;
- recoverable archive after 90 days;
- a pre-run backup with five retained snapshots; and
- model-assisted consolidation disabled by default.

With consolidation disabled, routine curation is deterministic and does not require an auxiliary model. Consolidation into umbrella skills is opt-in.

Archiving is recoverable rather than deletion. Pinned artifacts are protected from lifecycle transitions, while content fixes may still be allowed where ownership policy permits.

## Separation of concerns

Hermes's implementation divides self-improvement into distinct responsibilities:

| Concern                      | Mechanism                                                           |
| ---------------------------- | ------------------------------------------------------------------- |
| Detect a possible lesson     | Foreground judgment and periodic background review                  |
| Decide whether it is durable | Prompt policy plus deterministic exclusions                         |
| Route the lesson             | User profile, memory, existing skill, support file, or new umbrella |
| Find the owner               | Loaded-skill preference followed by library search                  |
| Author a candidate change    | Foreground or forked model                                          |
| Authorize mutation           | Tool-level ownership and provenance guards                          |
| Prevent stale writes         | Read-before-write enforcement                                       |
| Persist                      | Markdown and packaged skill files                                   |
| Observe use                  | `.usage.json` telemetry                                             |
| Maintain the library         | Deterministic curator plus optional model consolidation             |
| Recover                      | Archives, snapshots, and rollback commands                          |

This separation is more important than any individual prompt string.

## Strengths

1. **Clear fact/procedure distinction.** Memory and skills have different semantic roles.
2. **Existing-owner preference.** The system resists uncontrolled growth of narrow skills.
3. **Support-file model.** Detailed evidence can be retained without bloating the primary instructions.
4. **Post-response review.** Learning does not add foreground response latency.
5. **Policy near the write boundary.** Tool descriptions and deterministic guards reinforce prompt policy.
6. **Ownership-aware automation.** Human and external artifacts are protected from autonomous curation.
7. **Read-before-write enforcement.** Review agents cannot blindly modify unseen content.
8. **Recoverable lifecycle.** Stale content is archived with backups rather than silently deleted.
9. **Configurable review cadence.** Trigger intervals can change without rewriting the policy prompts.

## Risks and limitations

1. **Prompt-policy duplication.** Similar rules appear in foreground guidance, background prompts, and tool descriptions; these can drift.
2. **Threshold ambiguity.** “Five or more calls” in foreground guidance and a default automatic interval of ten iterations describe different mechanisms and can be misread as conflicting requirements.
3. **Active-review overcapture.** Telling the reviewer that most sessions should produce an update increases recall but may encourage low-value edits.
4. **Model-based classification remains fallible.** Deterministic exclusions reduce risk but do not prove that a proposed lesson generalizes.
5. **Markdown quality is not behavioral proof.** A structurally good skill can still degrade future agent performance without evaluations.
6. **Usage is an imperfect fitness signal.** Frequent loading does not prove correctness, and infrequent use does not prove obsolescence.
7. **Background work is best-effort.** Failure of a daemon review must not invalidate the completed user task, but learning can therefore fail silently or be deferred.
8. **Local customization can create hidden behavior.** `SOUL.md`, `USER.md`, and local skills affect decisions beyond the repository defaults.

## Lessons for Claude Self-Improvement

### Adopt

- Keep facts, procedures, enforced rules, and temporary state as separate artifact classes.
- Search loaded and existing artifacts before creating anything new.
- Prefer broad class-level skills with linked support files.
- Run learning review after the primary task completes.
- Put authorization, ownership, and read-before-write checks in deterministic code, not only prompts.
- Record provenance and usage outside human-readable instruction artifacts.
- Archive recoverably and back up before curation.
- Keep library-wide consolidation separate from per-session capture.
- Treat user corrections as higher-value evidence than agent inference.

### Strengthen beyond Hermes

The Claude plugin specifications should retain stronger first-release controls:

- explicit invocation before automatic review;
- review-only mutation for human-authored artifacts;
- exact diffs before approval;
- journaled filesystem mutation and reconciliation;
- deterministic validation before installation;
- redacted evidence handling;
- fresh-session discovery tests; and
- behavioral evaluations before automatic promotion.

Hermes demonstrates a mature routing and curation architecture. It does not eliminate the need for evaluation-driven promotion. A future Claude implementation should measure whether a proposed skill improves behavior rather than treating a plausible Markdown patch as sufficient evidence.

## Recommended mapping to the Claude plugin

| Hermes concept         | Claude Self-Improvement analogue                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `USER.md`              | Supported user-preference artifact controlled by plugin policy; do not mutate Claude-managed auto-memory without a documented contract |
| `MEMORY.md`            | Plugin-owned durable fact store or reviewed rule artifact                                                                              |
| `SKILL.md`             | Personal or project Claude skill                                                                                                       |
| Background review fork | Post-task reviewer invoked explicitly in Phase 1 and automatically only in later phases                                                |
| `skill_manage` guards  | Deterministic Go mutation policy and ownership checks                                                                                  |
| `.usage.json`          | SQLite metadata and/or sidecar provenance, reconciled against filesystem hashes                                                        |
| Curator                | Engine-event curator introduced in Phase 3                                                                                             |
| Curator backup         | Mutation journal, backup, rollback, and reconciliation workflow                                                                        |
| Fresh session reuse    | Packaged Claude Code session acceptance test                                                                                           |

## Conclusion

Hermes's self-improvement capability is not a single “remember this” prompt. It is a layered control system:

1. prompts detect and classify lessons;
2. an explicit routing hierarchy chooses the owning artifact;
3. tool-level guards authorize or reject writes;
4. files preserve durable knowledge;
5. telemetry records provenance and use; and
6. a recoverable curator manages long-term library shape.

The most reusable architectural insight is that learning quality depends less on generating new instructions than on **routing verified evidence to the correct existing owner under enforceable mutation policy**.
