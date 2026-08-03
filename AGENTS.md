# Agent instructions

## Scope

This repository develops a self-improvement plugin and local learning engine for Claude Code surfaces.

## Source of truth

- The current normative target is `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.
- Earlier architecture and phase documents under `docs/hypothetical-extensions/specs/` are non-normative research material.
- Current Claude Code behavior must be checked against official documentation at `https://code.claude.com/docs/` before implementation relies on it.

## Specification status

**Never mark a specification, slice, or acceptance criterion as done, implemented, complete, or passing without having first observed the evidence for it in this session.** Evidence means a command that ran and a result that was read: a passing test, an observed output, a verified artifact. Code being written is not evidence. Tests existing is not evidence. A run that was started, skipped, timed out, or interrupted is not evidence.

Where evidence is partial, say exactly which part is covered and which is not, in the status line itself. A specification whose checks have never passed is `Implemented; unverified`, not `Implemented`. Downgrade a status the moment its evidence is invalidated.

## A new finding gets its own specification

**Work that discovers a question does not own that question.** When a specification's own runs turn up something it did not set out to answer, the finding goes into a new numbered specification and **the original is not edited at all** — no summary paragraph, no section, no forward link. The new specification carries the backreference and the account of how the finding was discovered. References point from the newer document to the older one, never the reverse.

This is the default, not a judgement call. The only edit a finding may cause in the original is to its own status line, and only when the finding changes whether *its own* acceptance criteria are met.

The reason is that a specification is answerable. It states criteria, they are observed, and it closes. Anything appended to it afterwards makes a finished document read as unfinished, and a forward link to an open question does it just as effectively as a section would — a reader arriving at a closed specification should find no thread left dangling out of it. The finding is better served too: filed as an aside in someone else's argument it gets none of the framing it needs, and carrying its own discovery context costs the new document one paragraph.

A finding specification is not a design. It carries:

- the measurement, with its numbers and the runs that produced them;
- every hypothesis already eliminated, and what eliminated it, so nobody pays twice for the same answer;
- what would settle it, naming the instrument and saying honestly whether that instrument exists; and
- what closing it looks like — including deciding it is not worth the cost, which is a legitimate outcome and must be written down as one rather than left to lapse; and
- how it was found, which is the context the original would otherwise have had to keep.

Worked example: [Spec-0002](docs/specs/0002-pty-wake-harness.md) met every criterion it set, and its runs exposed a reviewer asymmetry it never scoped. The asymmetry became [Spec-0005](docs/specs/0005-reviewer-decline-asymmetry.md), which cites the runs that produced it. Spec-0002 says nothing about it and closed.

The same rule governs building for a finding: do not schedule work whose only justification is a question nobody has framed. Instrumentation proposed to answer an open finding stays behind a named hypothesis that its output could confirm or kill — see [Spec-0004 section 13](docs/specs/0004-plugin-execution-tracing.md#13-implementation-sequence).

## Development rules

- Deliver the Hermes-style experiential-learning vertical slice before introducing hypothetical extensions.
- Complete the user's task before learning review; review failure must not invalidate completed work.
- Ordinary experiential learning must not require user-authored behavioral test suites.
- Never infer that Claude surfaces share a filesystem, home directory, plugin cache, or process.
- Do not write directly to Claude configuration, memory, skill, or hook files without exact review, backup, and rollback.
- Treat Claude-managed auto-memory as read-only until Anthropic documents a supported external mutation contract.
- Do not store prompts, assistant responses, credentials, environment variables, or transcript bodies in telemetry.
- Use redacted fixtures in tests. Never copy live Claude transcripts or authentication state into the repository.
- Prefer deterministic classification filters before invoking an LLM reviewer.
- Search for and patch an existing artifact before creating a new skill or rule.
- Human-authored artifacts remain review-only.
- Use conventional commits.
- Commit at checkpoints as meaningful progress is achieved, rather than accumulating a whole task into one commit at the end.
- Add executable acceptance tests for every MVP behavioral requirement.

## Documentation consistency

When the MVP changes, update together:

- `README.md`;
- `docs/specs/README.md`; and
- `docs/specs/0001-hermes-style-experiential-learning-mvp.md`.

Do not rewrite hypothetical extension specifications merely to match the MVP. Validate relative Markdown links before committing.

## Debugging

When running `make wake` always capture output to a file, running it costs real money.
