# Spec-0004: Phase 3 — Skill curator

- **Status:** Proposed
- **Date:** 2026-07-28
- **Target release:** `v0.3`
- **Depends on:** Packaged Phase 1 core and the reviewed mutation/recovery contract from Phase 2A; Phase 2B automatic updates are not required

## Summary

Phase 3 manages the lifecycle of agent-created knowledge without allowing a background process to erase or silently rewrite human knowledge.

The curator tracks engine-owned lifecycle activity, identifies aged or overlapping agent-owned artifacts, and produces consolidation or archival proposals. Deterministic maintenance may update metadata automatically. Semantic consolidation remains reviewable.

## Goals

1. Measure only lifecycle events the engine directly owns and can prove.
2. Identify aged, overlapping, duplicate, and contradictory agent-owned artifacts.
3. Prefer rich umbrella skills over many narrow one-off skills.
4. Move detailed, session-specific material into skill references where appropriate.
5. Archive reversibly; never automatically delete.
6. Keep curation off the critical path of normal Claude responses.
7. Expose every recommendation with evidence and an exact diff.

## Ownership boundary

The curator may automatically mutate only its own activity and lifecycle metadata.

It may propose changes to:

- agent-owned skills;
- agent-owned rules and memory entries;
- mixed-ownership artifacts, with explicit review; and
- human-authored artifacts, as suggestions only.

It may never automatically:

- delete any knowledge artifact;
- alter human-authored content;
- edit hooks, settings, permissions, MCP configuration, or executables;
- merge artifacts across user/project scope; or
- publish a skill or repository change.

## Activity telemetry

Claude Code exposes no verified general `SkillInvoked` hook. Absence of engine events therefore cannot prove that Claude did not discover or invoke a skill. The curator does not label a skill “unused” from missing model-invocation telemetry.

Allowed engine-owned telemetry:

- artifact ID and canonical path hash;
- explicit proposal, engine command, mutation, rejection, rollback, archive, and restore counts;
- first and last activity timestamps;
- current lifecycle state;
- surface class: CLI, VS Code, or Desktop Local;
- engine/plugin version; and
- error class.

Forbidden telemetry:

- user prompts;
- assistant responses;
- transcript excerpts;
- file contents;
- file paths in shared reports;
- environment-variable values;
- credentials or account identifiers; and
- project names unless explicitly enabled locally.

## Lifecycle states

```text
active -> idle -> stale -> archived
   ^        |       |         |
   +--------+-------+---------+
          restore/use
```

- **active:** changed or explicitly acted on through the engine recently.
- **idle:** no recent engine-owned activity, but below the stale threshold; this does not mean Claude failed to use it.
- **stale:** eligible for review or archive proposal based on age and engine-owned history, never on an unsupported claim about model invocation.
- **archived:** removed from Claude discovery but retained with manifest and restoration path.
- **pinned:** orthogonal flag preventing automatic state progression and automated review proposals.

Thresholds are configurable. New installations start conservatively with automatic archival disabled.

## Analyses

### Duplicate detection

Use deterministic text fingerprints and structural metadata to produce candidate groups. An LLM may assess semantic overlap only after deterministic narrowing.

A duplicate report shall distinguish:

- byte or normalized-text duplicates;
- same trigger with overlapping procedure;
- same procedure with different scope;
- one umbrella skill plus a narrower extension;
- contradictory instructions; and
- false-positive topical similarity.

### Consolidation

A consolidation proposal shall:

1. name the target umbrella artifact;
2. preserve unique triggers, pitfalls, and verification steps;
3. move bulky supporting material to `references/`;
4. retain provenance for absorbed artifacts;
5. show the exact resulting diff;
6. define restoration behavior; and
7. require user approval.

### Archival

Archival is a reversible move into the engine archive with:

- original canonical path;
- content hash;
- ownership and provenance;
- reason and evidence;
- archive timestamp;
- replacement/umbrella artifact ID when applicable; and
- a tested restore command.

No automatic process permanently deletes archive contents. Pruning requires an explicit separate user action and is outside `v0.3`.

## Invocation and scheduling

Required invocation modes:

- explicit `/self-improvement:curate`;
- `claude-si curate scan --json`;
- `claude-si curate propose --json`; and
- `claude-si curate apply <proposal-id>` after approval.

A scheduled macOS launchd job may be added as an optional installer choice only after the manual curator passes the release gate. Scheduling must not be required for `v0.3`.

## Failure behavior

- Missing or corrupt activity data produces a diagnostic and a rebuild from provenance where possible.
- Analyzer uncertainty creates no proposal.
- Archive destination failure leaves the source untouched.
- Restore collision requires review; it never overwrites the current artifact.
- Curator failure cannot block Claude startup, response completion, or candidate capture.

## Acceptance gate

Phase 3 is complete only when:

1. Required Phase 1 and Phase 2A tests continue to pass; Phase 2B tests run only when automatic updates are enabled in the artifact under test.
2. Telemetry records only engine-owned lifecycle events without prompt, response, credential, or content leakage.
3. Pinned artifacts never progress automatically.
4. Human and mixed-ownership artifacts are never silently changed.
5. Duplicate fixtures produce the expected groups and preserve distinct procedures.
6. Contradictory fixtures are reported rather than merged.
7. Consolidation proposals preserve unique triggers, steps, pitfalls, and verification.
8. Archival removes an artifact from Claude discovery while retaining a complete restoration record.
9. Restore recreates the byte-identical original when no collision exists.
10. Curator crashes and timeouts do not affect normal Claude operation.
11. The exact checksummed artifact passes strict validation, version handshake, real executable resolution, curator proposal/rejection/apply, crash recovery, reload, uninstall, archive, and restore on every surface certified for that release.
12. No report infers that a skill was unused merely because no engine-owned event exists.

## Non-goals

Phase 3 does not:

- permanently delete artifacts;
- publish skills;
- provide organization-wide curation;
- synchronize state between hosts;
- mutate account-synchronized Cowork skills; or
- require a continuously running daemon.
