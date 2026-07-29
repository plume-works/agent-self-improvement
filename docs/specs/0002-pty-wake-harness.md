# Spec-0002: Automated verification of the asynchronous wake

- **Status:** Proposed; not implemented
- **Scope:** Test tooling only. No change to the plugin, its hooks, or its mutation protocol.
- **Depends on:** [Spec-0001](0001-hermes-style-experiential-learning-mvp.md), implemented

## 1. Problem

Nine of the ten checks in the packaged smoke test run headlessly and assert on structured data. One does not.

`make smoke` drives a real Claude Code session over `--input-format stream-json --output-format stream-json --include-hook-events`, which makes hook execution observable as JSON rather than as terminal text to scrape. Check 2 — that an asynchronous review wakes an idle session — cannot be observed that way.

This was measured rather than assumed. A probe plugin registering a `Stop` hook with `asyncRewake` and exiting 2 after a delay, run under `claude -p` with standard input held open, produced:

```text
system/hook_started   hook_event: "Stop"      the hook ran
result                stop_reason: "end_turn" the turn ended
(no further events, with stdin open for a further 25 seconds)
```

The hook fired and exited 2. No follow-up turn appeared. The documented behavior — "an `asyncRewake` hook that exits with code 2 wakes Claude immediately even when the session is idle" — describes an interactive session; a print-mode session has no idle state to wake into, because it finishes at `result`.

Check 2 is therefore the one place where the packaged plugin's most distinctive behavior is confirmed by a person watching a terminal.

## 2. Current mitigation

`make smoke` launches a real interactive session for check 2, in a scratch repository it has already prepared, with instructions printed to the terminal. Afterwards it verifies what is machine-checkable — that a candidate record exists, that the reviewer ran, that diagnostics are clean — and asks the operator one question about what only they could see.

This costs about two minutes and no setup. It is not a blocker for the MVP. What it does not give is a signal in continuous integration, or protection against a regression that silently stops the wake from arriving.

## 3. Proposal

Add an optional harness that drives a pseudo-terminal session and observes the wake directly.

### 3.1 Mechanism

1. Allocate a pty with the standard library's `pty` module. No third-party dependency is needed for the process control itself; the difficulty is in the output, not the plumbing.
2. Launch `claude --plugin-dir <plugin>` with the pty as its controlling terminal, in a prepared scratch repository.
3. Write a correcting exchange to the pty, one keystroke sequence per turn, waiting for the prompt to return between them.
4. After the final turn, send nothing. Read from the pty until either a wake marker appears or a timeout expires.
5. Assert on plugin state rather than on the screen wherever possible: a candidate record, a `pending.json` entry, an `awaiting` flag in `counters.json`.
6. Terminate the session and assert the exit was clean.

### 3.2 What may be asserted on screen

Only the arrival of the wake, and only by a marker the plugin itself controls. The harness must not assert on Claude's prose, on box drawing, on spinner frames, or on anything else the interface owns.

A dedicated marker is worth introducing for this: the wake message already begins with a fixed `self-improve:` prefix, and the harness should search for the candidate identifier it can independently read from disk, rather than for wording.

### 3.3 What must not be attempted

- Asserting that a proposal was "presented verbatim" by matching rendered text. That is a model grading a model through a terminal renderer, and it is weaker evidence than the byte comparison the headless checks already make.
- Driving the apply, reject, or rollback commands through the pty. Those are already covered deterministically, and typing them through a harness would prove only that a program can type.
- Screen-diffing. Claude Code redraws, uses an alternate screen, and reflows on resize.

## 4. Risks

This harness is expected to be the least stable component in the repository.

- **Interface coupling.** Anything matched on screen is coupled to a renderer with no compatibility contract. Keep the matched surface to one plugin-controlled marker.
- **Timing.** The wake arrives after a real model call. A timeout long enough to be reliable is long enough to make the suite slow, and a flaky assertion here is worse than no assertion.
- **Terminal environment.** Dimensions, `TERM`, and color support all change what is emitted. Pin them explicitly.
- **Cost.** Every run spends model usage on a real review.

Because of these, the harness must be opt-in — its own marker and its own make target — and must never gate `make test` or `make check`.

## 5. Security note

A pty harness can type `/self-improve:apply` into a session. This does not weaken the mutation protocol, and it does not reveal a flaw in it: the trust boundary defined in [Spec-0001 section 5.2](0001-hermes-style-experiential-learning-mvp.md#52-userpromptexpansion) is a command typed into the session, and anything with write access to the terminal is inside that boundary already, as is anything that can run arbitrary commands as the user.

It is worth stating plainly rather than leaving implied: the protocol defends against a model deciding to mutate an artifact on its own, not against an attacker who already controls the user's terminal.

## 6. Acceptance

The harness is worth having only if it is more reliable than the manual check it replaces. It is accepted when it:

1. detects an arriving wake within a bounded timeout, in ten consecutive runs, with no failures;
2. fails when the wake genuinely does not arrive, demonstrated by disabling the `asyncRewake` flag;
3. asserts on plugin-controlled state and one plugin-controlled marker, and on nothing the interface renders;
4. leaves its scratch workspace under `tmp/` for inspection; and
5. runs behind its own target, excluded from `make test`, `make check`, and `make smoke`.

Until it meets those, the interactive step in `make smoke` remains the supported way to verify the wake.
