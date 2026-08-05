# Case study: Hermes Agent self-improvement system

## Status and scope

This document records a source-grounded case study of the self-improvement system in Hermes Agent. It describes how Hermes turns conversation outcomes into durable memory and reusable skills, how the relevant instructions are assembled, and which design lessons apply to Claude Self-Improvement.

This is descriptive evidence, not a normative requirement. Requirements for this repository remain under [`../../specs/`](../../specs/README.md).

### Inspected implementation

- Repository: [`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent)
- Source package version: `0.20.0`
- Inspected commit: `aec331899e4748739927fddf02a54327e64419a0`
- Prompt corpus: [source-faithful Python and human-readable copies](prompts/README.md)

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

| File | Responsibility |
|---|---|
| `agent/prompt_builder.py` | Defines foreground memory and skill guidance injected into the system prompt. |
| `agent/system_prompt.py` | Assembles identity, tool-aware guidance, project context, memory, and profile information. |
| `agent/background_review.py` | Contains the detailed post-turn memory and skill review prompts and launches the review fork. |
| `agent/turn_finalizer.py` | Checks review triggers and starts background review after the normal response. |
| `agent/agent_init.py` | Loads configured nudge intervals and initializes review counters. |
| `tools/memory_tool.py` | Defines the memory tool's operational instructions and persistence interface. |
| `tools/skill_manager_tool.py` | Defines skill mutation instructions and mutation guardrails. |
| `tools/skill_usage.py` | Tracks ownership, use, views, patches, state, and pinning. |
| `agent/curator.py` | Implements stale-skill and consolidation lifecycle operations. |
| `hermes_cli/config_defaults.py` | Defines curator defaults and other configuration defaults. |
| `$HERMES_HOME/SOUL.md` | Optional local identity and high-level continuity policy. |
| `$HERMES_HOME/memories/USER.md` | Persisted user profile and preferences. |
| `$HERMES_HOME/memories/MEMORY.md` | Persisted stable environmental facts and conventions. |
| `$HERMES_HOME/skills/**/SKILL.md` | Reusable procedural knowledge loaded into future sessions. |

### Prompt assembly

`agent/system_prompt.py` builds three broad tiers:

1. **Stable:** identity, tool-aware foreground memory/skill guidance, execution guidance, and platform/environment hints.
2. **Context:** caller instructions and project context such as `AGENTS.md`.
3. **Volatile:** the dynamic skills index, memory snapshot, `USER.md`, external memory, and session metadata.

Memory and skill guidance are tool-aware:

- memory guidance is injected only when the memory tool is available;
- skill guidance is injected only when `skill_manage` is available.

This prevents the prompt from instructing the model to perform persistence operations it cannot execute.

The skills index moved from the stable tier to the front of the volatile tier after the
earlier case-study snapshot. Skills are mutable during a session, so a rebuilt prompt can
change at that point. Keeping the index late preserves more of the reusable prompt-cache
prefix without hiding any skill from the model.

## Attached prompt corpus

The prompt material is attached in two parallel forms:

| Layer | Source-faithful Python | Rendered reading copy |
| --- | --- | --- |
| Foreground guidance and skill-index envelope | [`prompts/python/foreground.py`](prompts/python/foreground.py) | [`prompts/readable/foreground.md`](prompts/readable/foreground.md) |
| Background memory, skill, and combined review | [`prompts/python/background_review.py`](prompts/python/background_review.py) | [`prompts/readable/background-review.md`](prompts/readable/background-review.md) |
| Memory and skill-management tool schemas | [`prompts/python/tool_schemas.py`](prompts/python/tool_schemas.py) | [`prompts/readable/tool-schemas.md`](prompts/readable/tool-schemas.md) |
| Curator live and dry-run prompts | [`prompts/python/curator.py`](prompts/python/curator.py) | [`prompts/readable/curator.md`](prompts/readable/curator.md) |

The Python copy retains interpolation and composition exactly. The reading copy joins
Python string literals and labels every substitution. It is not presented as a captured
live request because the skill inventory, memory content, home path, curator candidates,
platform context, and optional auxiliary-model digest depend on runtime state.

This corpus includes tool descriptions because they are part of the model-visible prompt
surface. Looking only for variables named `PROMPT` would omit much of Hermes's operational
policy.

## What the review model actually receives

The background reviewer does not run under a small standalone reviewer system prompt. On
the default same-model path, its effective input is layered as follows:

```text
parent's cached Hermes system prompt
  ├── foreground MEMORY_GUIDANCE / SKILLS_GUIDANCE
  ├── dynamic <available_skills> index
  ├── current MEMORY.md / USER.md snapshots
  └── ordinary identity, project, platform, and execution guidance

parent conversation snapshot
  └── full history on the same-model path

selected review user message
  ├── memory-only, skill-only, or combined review prompt
  └── "only call memory and skill management tools" suffix

model-visible function schemas
  ├── memory policy and atomic operation grammar
  └── skill_manage policy and mutation grammar

runtime enforcement
  └── thread-local dispatch whitelist plus ownership/read-before-write guards
```

When review is explicitly routed to a different auxiliary model, the prompt cache is cold,
so Hermes replaces older history with a synthetic digest and retains the latest 24 messages
verbatim. On the default path it replays the complete snapshot to exploit the already-warm
prefix. In both cases the review message is appended after the completed conversation.

The fork has a maximum of 16 iterations. It shares the built-in memory store, but external
memory providers are disabled. Its memory and skill nudge counters are zeroed, recursive
review is disabled, and session persistence is disabled so the review harness and its reply
cannot be written into the user's canonical conversation. These are prompt-quality
preconditions: without them, the reviewer could learn from its own review instructions or
spawn another review.

Hermes keeps the parent's configured tool-schema surface byte-compatible for cache reuse,
then rejects non-memory/skill dispatch at runtime. The appended capability sentence tells
the model the narrower truth. This is a recurring pattern: prompt language steers the model,
while code enforces the boundary.

### Why the memory-only prompt is so short

Read in isolation, the memory-only review asks only whether the user revealed personal facts
or behavioral expectations. Its durability rules live elsewhere:

1. foreground `MEMORY_GUIDANCE` defines the seven-day staleness test and rejects progress
   logs, issue identifiers, commit hashes, and temporary state;
2. the memory tool description repeats what to save, what to skip, and the fact/procedure
   boundary; and
3. the memory schema makes an atomic batch the preferred mutation shape.

The short review string selects the task. The inherited system guidance and tool schema
define how to perform it. Copying only `_MEMORY_REVIEW_PROMPT` would discard most of the
behavior.

### Why loaded-skill context matters

The skill-review prompt's first routing preference is the skill actually loaded or viewed
during the session. Hermes can ask the model to “look back” because the review receives the
conversation replay, including prior `skill_view` calls and results. A bounded reviewer that
does not receive transcripts cannot reproduce this instruction by wording alone; it must be
given deterministic metadata naming which durable artifacts were used.

The dynamic skills index supplies broad discovery context, while `skills_list` and
`skill_view` provide the exact current owner before a write. Hermes truncates long index
descriptions to 57 characters plus `...`, so the tool description explicitly requires the
trigger to fit in the first 57 characters. That is an end-to-end prompt contract: authoring
quality affects future routing quality.

## Prompt-design mechanics

The strongest parts of the prompt are concrete decision mechanics rather than tone:

1. **An active prior after a trigger.** The skill reviewer says that doing nothing is a
   missed opportunity, while retaining an explicit `Nothing to save.` exit for genuinely
   signal-free work.
2. **Natural correction examples.** Phrases such as “stop doing X” and “this is too
   verbose” teach the classifier how real users express preferences without a formal request
   to remember them.
3. **A routing ladder before creation.** Loaded owner, existing umbrella, support file, then
   new class-level umbrella is an ordered decision, not a list of equally weighted options.
4. **A name veto.** PR numbers, exact errors, feature codenames, and today's debugging task
   are forbidden as new-skill identities; a name that makes sense only today is evidence the
   material belongs under an existing class.
5. **Explicit negative examples.** Environment setup state, temporary retries, negative
   capability claims, one-off narratives, and unresolved failures are rejected in the
   language most likely to tempt over-learning.
6. **Action grammar near the action.** Tool descriptions say when to create or patch, what a
   good skill contains, how to identify exact replacement text, and how to represent
   consolidation intent.
7. **Actor-specific policy.** Foreground `skill_manage` may patch a pinned skill with the
   user present; the autonomous review prompt may not. The write guard uses review origin to
   enforce that distinction.
8. **Separate capture from library gardening.** A single-session review can flag overlap,
   but the curator owns large-scale consolidation and uses a different prompt, tool budget,
   candidate set, backup, and report contract.

### Fact, preference, and procedure are not one class

Hermes deliberately uses overlapping persistence for some user corrections:

- `USER.md` records declarative facts about the person, such as a stable communication
  preference;
- `MEMORY.md` records stable environmental facts and conventions;
- a skill records the imperative procedure for a class of task, including a user's preferred
  workflow or presentation when it changes how that task should be performed.

The apparent duplication is intentional. A fact answers “what is true about the user or
environment?” A skill answers “how should this class of work be done?” The prompt warns
against storing an imperative procedure as memory because it will be injected as an
unscoped standing command later.

## How these prompts evolved

The current wording is the residue of observed failure modes, not one clean-room prompt
draft:

| Upstream change | Observed problem | Prompt or control response |
| --- | --- | --- |
| `a1220977` / `17c72f17`, 2026-04-12 | Models skipped relevant skills under “clearly matches” wording | Lower the threshold to partial relevance, make loading mandatory, and remove the easy escape hatch. |
| `db60c982`, 2026-04-19 | Imperative memories were re-read as future directives | Require declarative facts and give paired good/bad examples. |
| `1d4218be`, 2026-04-28 | Review passes defaulted to `Nothing to save.` and lost style corrections | Add the active-update prior, natural-language correction examples, loaded-skill-first routing, support-file types, and class-level name veto. |
| `fa9383d2`, 2026-04-28 | The curator passively audited or kept distinct siblings | Ask the umbrella-class question, pre-empt the zero-usage and distinct-trigger bailouts, and enumerate three consolidation actions. |
| `6e5489c9`, 2026-05-09 | Session outcomes crowded durable memory | Name forbidden artifacts and introduce the seven-day staleness heuristic. |
| `af78449a`, 2026-05-18 | Review could rewrite bundled, hub, or pinned skills | Put protected classes in the review prompt as well as mutation policy. |
| `38c8a9c1`, 2026-06-18 | A near-full memory store caused multi-call consolidation thrash | Lead the tool schema with one atomic batch and a terminal “do not repeat” result. |
| `20871c1d`, 2026-06-30 | A reviewer could write from stale or absent skill context | Require the exact target to be viewed during that review turn before mutation. |
| `243a01d5` / `9b909115`, 2026-07-25 | Missing ownership metadata allowed one background write, then later refused the same action | Make prompt and enforcement agree, require positive curator ownership, and fail closed on missing or unreadable provenance.                   |
| `2ace68ad`, 2026-07-31 | Failed attempts could be persisted as a “reliable workflow” | Explicitly reject unresolved failures and forbid dressing dead ends up as best practice. |

The curator rewrite has unusually concrete upstream evidence: its commit message records
three live passes over 346 agent-created skills. The old prompt archived 3 entries; the
sharpened umbrella prompt ultimately reduced 346 entries to 118 while preserving archived
content as references. This is useful design evidence, but not a controlled evaluation:
the runs changed the prompt between attempts, used one personal library, and measured
library shape rather than downstream task quality.

## Quality comes from prompts; reliability comes from the stack

| Desired property | Prompt contribution | Deterministic contribution |
| --- | --- | --- |
| Catch terse corrections | Natural-language examples and active prior | Periodic trigger counters decide when review runs. |
| Avoid stale facts | Seven-day rule and concrete forbidden examples | Memory size bounds and atomic operations limit damage. |
| Avoid skill sprawl | Loaded-owner ladder, class-level target, name veto | Ownership metadata and current library inventory constrain targets. |
| Avoid blind overwrite | `skill_view` instruction | Read-before-write guard rejects unseen targets. |
| Respect human ownership | Protected-skill explanation | Background origin, pin, provenance, and external-path guards fail closed. |
| Avoid retry thrash | One-call batch instruction | Atomic final-state validation applies all or nothing. |
| Recover from curation | Archive-only and structured consolidation intent | Pre-run backup, archive state, and rollback preserve recoverability. |
| Prevent recursive learning | Reviewer wording limits tools | Nudge counters, persistence, external memory, and recursive review are disabled in the fork. |

This distinction is the main adoption constraint for this repository. Hermes's active
language can improve recall, but copying its permission to mutate would weaken the MVP.
The reusable unit is the classification and routing rubric paired with this repository's
existing review-only, exact-diff, one-time-approval control plane.

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
