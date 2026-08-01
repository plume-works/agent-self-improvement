# Specification index

Only the Hermes-style experiential-learning MVP is on the implementation path:

- [Spec-0001: Hook-driven experiential learning plugin MVP](0001-hermes-style-experiential-learning-mvp.md) — **Accepted; implemented.** Offline suite and nine of ten packaged smoke checks observed passing. The tenth, the asynchronous wake, is not yet evidenced.
- [Spec-0002: Automated verification of the asynchronous wake](0002-pty-wake-harness.md) — **Implemented; partially verified.** Test tooling only. The harness runs behind `make wake`; its model-free self-checks, its harness self-checks (`make test-harness`), and its live negative control pass, so acceptance criterion 2 is evidenced. The positive check has never passed — in the last run review ran and stored no candidate — so criterion 1 is not. The interactive step in `make smoke` remains the supported way to verify the wake.

Statuses here follow the evidence rule in [`AGENTS.md`](../../AGENTS.md#specification-status): nothing is marked done before a command has been run and its result read.

The previous architecture and phase specifications have been moved unchanged into [`docs/hypothetical-extensions/specs/`](../hypothetical-extensions/specs/README.md). They are research material for possible later extensions, not accepted requirements, dependencies, or release gates for the MVP.
