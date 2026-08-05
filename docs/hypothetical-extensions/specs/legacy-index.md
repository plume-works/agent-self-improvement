# Specification index

Specifications are normative unless marked otherwise. Later specifications may refine an earlier design only by naming the changed requirement explicitly.

| Spec                                                                                                                      | Status                           | Release boundary                  | Depends on                                         |
| ------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | --------------------------------- | -------------------------------------------------- |
| [Spec-0001: Initial system design](0001-initial-system-design.md)                                                         | Proposed                         | Architecture and invariants       | None                                               |
| [Spec-0002: Phase 1 — Review-only local core](0002-phase-1-review-only.md)                                                | Proposed                         | `v0.1`–`v0.1.3` incremental gates | Spec-0001                                          |
| [Spec-0003: Phase 2 — Existing-artifact patches and trusted automatic updates](0003-phase-2-trusted-automatic-updates.md) | Proposed                         | `v0.2` / `v0.2.1`                 | Packaged Phase 1 core                              |
| [Spec-0004: Phase 3 — Skill curator](0004-phase-3-skill-curator.md)                                                       | Proposed                         | `v0.3`                            | Packaged Phase 1 core + Phase 2A mutation/recovery |
| [Spec-0005: Phase 4 — Additional environments](0005-phase-4-additional-environments.md)                                   | Proposed, intentionally deferred | Independent adapters              | Exact core contract consumed by each adapter       |

## Release sequence

```text
Spec-0001 design
      |
      v
Phase 1: explicit CLI tracer bullet --------------------------> v0.1
      |
      +--> automatic capture --------------------------------> v0.1.1
      +--> VS Code Local certification ----------------------> v0.1.2
      +--> Desktop Code Local certification -----------------> v0.1.3
      |
      v
Phase 2A: reviewed existing-artifact patches ----------------> v0.2
      |
      v
Phase 2B: narrowly trusted automatic updates ----------------> v0.2.1
      |
      v
Phase 3: engine-event curation and archival -----------------> v0.3

Packaged Phase 1 core may independently feed:
      +--> Desktop Chat/Cowork adapter
      +--> devcontainer topology
      +--> SSH/remote topology
```

Phase 4 is not one coupled release. Each environment adapter depends only on the exact packaged core contracts it consumes and must prove its own storage, execution, authentication, and rollback boundaries.

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
