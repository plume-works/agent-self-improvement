# Specification index

Only the Hermes-style experiential-learning MVP is on the implementation path:

- [Spec-0001: Hook-driven experiential learning plugin MVP](0001-hermes-style-experiential-learning-mvp.md) — **Accepted; fully implemented.** Every slice is delivered and the section 15 acceptance gate is met.
- [Spec-0002: Automated verification of the asynchronous wake](0002-pty-wake-harness.md) — **Accepted; implemented.** Test tooling only. The smoke check that cannot run headlessly is automated by the pty harness behind `make wake`; the interactive step in `make smoke` remains as a fallback.

The previous architecture and phase specifications have been moved unchanged into [`docs/hypothetical-extensions/specs/`](../hypothetical-extensions/specs/README.md). They are research material for possible later extensions, not accepted requirements, dependencies, or release gates for the MVP.
