# Spec-0001: Hermes-style experiential learning MVP

- **Status:** Proposed MVP
- **Scope:** Standalone Claude Code CLI on one local user account
- **Supersedes for MVP planning:** the earlier multi-phase specifications, now retained as [hypothetical extensions](../hypothetical-extensions/specs/README.md)

## 1. Product goal

Claude should learn from completed work in the same practical sense that Hermes does:

> recognize a verified correction or hard-won workflow, extract the reusable lesson, route it to the right durable artifact, and make that lesson available in later sessions.

The user should not have to design test procedures, maintain evaluation datasets, or operate a prompt optimizer. Ordinary learning is grounded by direct evidence such as:

- an explicit user correction;
- a failed command or approach followed by a verified successful one;
- a reusable workflow that produced the requested result;
- repeated friction across sessions; or
- an explicit request to remember an approach.

## 2. MVP experience

The narrow end-to-end loop is:

```text
completed Claude Code work
        |
        v
post-response learning review
        |
        v
classify: task-only / discard / durable fact / procedure / rule
        |
        v
search existing instructions, rules, and skills for the owner
        |
        v
propose one exact addition or patch
        |
        v
user reviews and approves or rejects it
        |
        v
backup, apply, verify discovery in a fresh session, and allow rollback
```

The primary task completes before review begins. Failure or cancellation of learning must not invalidate the user's completed work.

An explicit command remains available as a high-signal front door when the user wants immediate reflection. Automatic review may identify candidates, but it never authorizes a durable write.

## 3. Required behavior

### 3.1 Evidence and classification

The reviewer must:

1. identify the concrete evidence and verified outcome;
2. remove incident-specific and temporary details;
3. state the reusable lesson and a counterexample or applicability boundary;
4. reject task progress, completion logs, commit identifiers, credentials, raw transcripts, and unverified guesses; and
5. classify the result as task-only, discard, durable fact, reusable procedure, or deterministic rule proposal.

### 3.2 Search before creation

Before proposing a new artifact, the system searches the currently loaded and existing Claude instructions, rules, and skills.

Preference order:

1. patch the currently loaded owner;
2. patch an existing class-level umbrella;
3. add a linked reference to an existing umbrella; or
4. propose a new skill only when no suitable owner exists.

The MVP may create one new personal skill or patch one existing explicitly selected artifact. It must not perform broad configuration cleanup or multi-artifact consolidation.

### 3.3 Review and mutation

A proposal must show:

- destination and scope;
- exact old and new content;
- evidence summary;
- applicability and counterexample;
- why the selected artifact owns the lesson; and
- backup and rollback location.

The model may propose but may not approve its own write. Rejection leaves the target unchanged.

Before applying an approved proposal, the implementation must re-read the target and refuse stale, conflicting, symlinked, or out-of-scope paths. It creates a recoverable preimage before mutation, installs the approved bytes, verifies the resulting bytes, and exposes a rollback operation.

### 3.4 Later-session proof

Acceptance requires a fresh Claude Code CLI session to discover the created or patched artifact through the documented Claude Code mechanism. The MVP verifies loading and invocation; it does not require the user to author behavioral benchmarks for every skill.

## 4. Explicit non-goals

The MVP does **not** include:

- SkillOpt, GEPA, or another prompt optimizer;
- user-authored train/validation/test datasets;
- model-generated rubrics treated as proof of improvement;
- broad or unattended transcript harvesting;
- automatic adoption of model-authored changes;
- autonomous edits to Claude-managed auto-memory;
- multi-artifact restructuring, deletion, or semantic consolidation;
- long-term usage scoring or stale-skill curation;
- VS Code, Desktop, SSH, devcontainer, cloud, or multi-user certification; or
- daemon, federation, vector-memory, distributed-training, or model-weight infrastructure.

These may be investigated later without becoming dependencies of the MVP.

## 5. Relationship to existing tools

### `/improve`

[`TerenceBristol/claude-improve`](../case-study/claude-improve/README.md) is a useful manual UX and reasoning baseline: explicit reflection, placement analysis, and one-finding-at-a-time review. It is not the trusted mutation boundary because it can inspect broad private state and directly edit multiple configuration classes without exact patch authorization or journaled recovery.

### SkillOpt-Sleep

[`microsoft/SkillOpt`](https://github.com/microsoft/SkillOpt) optimizes textual guidance against mined or supplied tasks. That is not the MVP's definition of experiential learning. If users do not maintain independent, meaningful evaluations, its model can mine the experience, propose the lesson, invent the criterion, and judge its own change. SkillOpt is therefore neither an MVP dependency nor a substitute for Hermes-style reflection and routing. It remains a hypothetical optional optimizer for a later, objectively testable, agent-owned skill.

### Learning Loop

[`robinslange/learning-loop`](../case-study/learning-loop/README.md) demonstrates useful instrumentation, validators, diagnostics, and shadow operation, but its knowledge-system, hook, daemon, retrieval, and mutation scope is intentionally outside this MVP.

## 6. MVP acceptance gate

The MVP is complete only when one packaged local workflow demonstrates all of the following:

1. a completed task containing a verified correction or successful workaround can trigger review after the primary response;
2. a no-lesson task produces no durable proposal;
3. the reviewer searches existing artifacts before proposing creation;
4. the user can inspect and reject an exact proposal with no target change;
5. approval applies only the reviewed bytes to one permitted artifact;
6. interruption or stale external edits fail without overwriting unexpected content;
7. a fresh Claude Code CLI session discovers the resulting skill or instruction;
8. rollback restores the verified preimage; and
9. persisted state and diagnostics contain no raw transcript, credential, prompt, or assistant-response body.

No optimization benchmark is required for this gate. The product claim is narrowly that Claude can retain a verified reusable lesson safely and make it available later—not that every retained lesson statistically improves all future behavior.

## 7. Deferred questions

Implementation should verify current public Claude Code plugin, hook, skill, and session seams before choosing its packaging and post-response trigger. If automatic post-response model review cannot be implemented through a supported seam, the MVP ships the same flow behind an explicit command rather than depending on private transcript formats or host credentials.
