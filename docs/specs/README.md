# Specification index

Specifications are normative unless marked otherwise. Later specifications may refine an earlier design only by naming the changed requirement explicitly.

| Spec | Status | Release boundary | Depends on |
| --- | --- | --- | --- |
| [Spec-0001: Initial system design](0001-initial-system-design.md) | Proposed | Architecture and invariants | None |
| [Spec-0002: Phase 1 — Review-only vertical slice](0002-phase-1-review-only.md) | Proposed | `v0.1` | Spec-0001 |
| [Spec-0003: Phase 2 — Trusted automatic updates](0003-phase-2-trusted-automatic-updates.md) | Proposed | `v0.2` | Phase 1 release gate |
| [Spec-0004: Phase 3 — Skill curator](0004-phase-3-skill-curator.md) | Proposed | `v0.3` | Phase 2 release gate |
| [Spec-0005: Phase 4 — Additional environments](0005-phase-4-additional-environments.md) | Proposed, intentionally deferred | Independent adapters after `v0.3` | Environment-specific |

## Release sequence

```text
Spec-0001 design
      |
      v
Phase 1: review-only local vertical slice --------------------> v0.1
      |
      v
Phase 2: narrowly trusted automatic updates -----------------> v0.2
      |
      v
Phase 3: usage-aware curation and archival ------------------> v0.3
      |
      +--> Desktop Chat/Cowork adapter (separate gate)
      +--> devcontainer topology (separate gate)
      +--> SSH/remote topology (separate gate)
```

Phase 4 is not one coupled release. Each additional environment must ship independently after proving its own storage, execution, authentication, and rollback boundaries.

## Status vocabulary

- **Proposed:** design exists but is not accepted by implementation evidence.
- **Accepted:** maintainers approve the design for implementation.
- **Implemented:** all named acceptance gates pass in the packaged artifact.
- **Superseded:** replaced by another named specification.

## Authoring requirements

Every phase specification must state:

1. user value and first observable result;
2. exact dependencies;
3. goals and non-goals;
4. ownership and trust boundaries;
5. failure behavior and rollback;
6. deterministic tests;
7. packaged-artifact smoke tests; and
8. evidence required before the phase can be declared complete.
