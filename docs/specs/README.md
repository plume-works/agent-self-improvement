# Specification index

The Hermes-style experiential-learning MVP remains the only accepted product implementation. A Codex integration is proposed separately and does not change the Claude MVP:

- [Spec-0001: Hook-driven experiential learning plugin MVP](0001-hermes-style-experiential-learning-mvp.md) — **Accepted; implemented.** The whole offline suite and nine of ten packaged smoke checks observed passing. The tenth, the asynchronous wake, is evidenced by the [Spec-0002](0002-pty-wake-harness.md) harness.
- [Spec-0002: Automated verification of the asynchronous wake](0002-pty-wake-harness.md) — **Implemented; verified.** Test tooling only. The harness runs behind `make wake`; its model-free self-checks, its harness self-checks (`make test-harness`), and both live checks were observed passing together (2026-08-01), and `make wake-repeat` then completed ten consecutive runs with no failure (2026-08-02). Every acceptance criterion in its section 6 has been observed. Five of those twenty checks skipped on a reviewer that stored no candidate, four of them on the negative control, which its section 8.3 records as unexplained.
- [Spec-0003: Codex integration for experiential learning](0003-codex-integration.md) — **Proposed; integration analysis only.** Maps every current Claude-specific seam to Codex, defines a dual-host adapter design, and records missing async wake, command-expansion provenance, generic tool-failure, strict no-tools, and path-scoped behavioral-rule parity. No Codex implementation or acceptance result has been observed.

Statuses here follow the evidence rule in [`AGENTS.md`](../../AGENTS.md#specification-status): nothing is marked done before a command has been run and its result read.

The previous architecture and phase specifications have been moved unchanged into [`docs/hypothetical-extensions/specs/`](../hypothetical-extensions/specs/README.md). They are research material for possible later extensions, not accepted requirements, dependencies, or release gates for the MVP.
