# Spec-0002: Automated verification of the asynchronous wake

- **Status:** Implemented; **verified**. The harness is `tests/smoke/pty_harness.py` and `tests/smoke/test_wake_pty.py`, run with `make wake`. Its model-free self-checks and its harness self-checks (`make test-harness`) pass. Both live checks were observed passing together (`make wake`, 2026-08-01, Claude Code 2.1.220): the wake arrived at an idle session for `cand-12f3c9117d4c`, and the negative control stored `cand-d5552db5fde5` and saw no wake when the `Stop` hook cannot signal. `make wake-repeat` then completed ten consecutive runs with no failure (2026-08-02). Every acceptance criterion in section 6 has been observed. What that does *not* say is that every run observes the wake: five of those twenty checks skipped, having no candidate staged to watch for.
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
- **Cost.** Every run spends model usage on a real review. The driven session is pinned to `sonnet` at `low` effort rather than inheriting the developer's CLI default, since nothing this harness observes depends on either: the session follows a written procedure. `SMOKE_MODEL` and `SMOKE_EFFORT` override them, and setting either empty restores the CLI default for reproducing a model- or effort-specific failure. Effort is passed as `--effort` rather than `CLAUDE_CODE_EFFORT_LEVEL` because that variable is inherited and would reach the reviewer subprocess inside the session, retuning the component under test. The reviewer keeps its own `SELF_IMPROVE_REVIEW_MODEL` and `SELF_IMPROVE_REVIEW_EFFORT`.

Because of these, the harness must be opt-in — its own marker and its own make target — and must never gate `make test` or `make check`.

## 5. Security note

A pty harness can type `/self-improve:apply` into a session. This does not weaken the mutation protocol, and it does not reveal a flaw in it: the trust boundary defined in [Spec-0001 section 5.2](0001-hermes-style-experiential-learning-mvp.md#52-userpromptexpansion) is a command typed into the session, and anything with write access to the terminal is inside that boundary already, as is anything that can run arbitrary commands as the user.

It is worth stating plainly rather than leaving implied: the protocol defends against a model deciding to mutate an artifact on its own, not against an attacker who already controls the user's terminal.

## 6. Acceptance

The harness is worth having only if it is more reliable than the manual check it replaces. It is accepted when it:

1. detects an arriving wake within a bounded timeout, in ten consecutive runs, with no failures;
2. fails when the wake genuinely does not arrive, demonstrated by disabling the `asyncRewake` flag;
3. asserts on plugin-controlled state and one plugin-controlled marker, and on nothing the interface renders;
4. leaves its scratch workspace where it can be inspected afterwards — one gitignored directory per run under `test-runs/`, so a later run of any target cannot overwrite it; and
5. runs behind its own target, excluded from `make test`, `make check`, and `make smoke`.

Until it meets those, the interactive step in `make smoke` remains the supported way to verify the wake.

## 7. Implementation notes

The harness is `tests/smoke/pty_harness.py`; the checks are `tests/smoke/test_wake_pty.py`, marked `pty` and run only by `make wake`. `make test`, `make check`, and `make smoke` all exclude that marker.

Three decisions differ from, or sharpen, what section 3 anticipated.

**Turn boundaries come from quiescence, not from a prompt.** Section 3.1 says to wait for the prompt to return between turns, but recognizing the prompt would mean matching what the interface renders, which section 3.2 forbids. The harness instead waits for the output stream to stop for eight seconds. While Claude works the renderer emits continuously; when it stops, the stream goes quiet. That is a property of a terminal program redrawing rather than of any version's layout.

**The on-screen match is normalized before comparison.** A 17-character candidate identifier wraps whenever it lands near the right margin, so escape sequences and all whitespace are stripped from both sides before the single match. Without this a wake that did arrive would be reported as missing. This is covered by a check that needs no model.

**The negative control suppresses the wake signal rather than the `asyncRewake` flag.** Section 6.2 proposed disabling the flag, but that control does not discriminate: without it the `Stop` hook still runs and still exits 2, synchronously inside the turn, so Claude is still told about the candidate and the marker still reaches the screen. The control would pass whether or not the wake worked. The harness instead runs a copy of the plugin whose `Stop` hook discards its exit code, leaving the gate, the reviewer, and the stored candidate exactly as they are and removing only the wake. A candidate is then required on disk — a control that observed nothing proves nothing — and the marker is required to be absent from the screen.

Two failure modes are separated in the assertions, because they have different causes and different fixes: review never ran or proposed nothing, versus a candidate that exists while no wake arrived. Only the second is a wake failure.

**A review that stored no candidate skips the check rather than failing it.** Both live checks need a candidate before they can observe anything: one watches for a wake carrying its identifier, the other for the absence of one. With nothing stored there is no identifier and no wake either way, and the run has observed nothing about the mechanism under test.

That is not a rare case. Replaying a reconstruction of the scripted exchange's evidence bundle through the real reviewer 56 times declined 3 of them with `transient_state`, on a bundle the other 53 proposed from. Live it is commoner still: the ten-run loop of section 8 declined 5 of 20. Failing on a decline would have made a red run the *expected* outcome of `make wake`, every one of them pointing at a wake that was never in question. A harness that cries wolf at that rate stops being read.

So a review that ran and stored nothing skips, carrying its journalled reason, the same way a check whose model call never went through already does. A skip is not a pass: `-rs` prints the reason at the end of every run, and the evidence in section 8 still requires observing these checks pass. What must never skip is a review that never ran, or one that stored nothing and journalled nothing — those are the exchange and the gate failing, which is what these checks exist to catch.

### 7.1 Bounded runtime

**A working run of either live check finishes in well under a minute. Every check is bounded end to end by a single wall-clock budget of three minutes, and no wait in the harness may block without a deadline.**

This is normative rather than a tuning preference. The first implementation gave each step a generous timeout — five minutes for a turn, two and a half for the wake — and no overall limit. Each wait was inside its own limit and a check still occupied a terminal for eighteen minutes without reaching a verdict. A harness that hangs is worse than the manual procedure it replaces: the manual one at least ends when the person walks away.

The budget is one `Deadline` shared by the session and every wait taken from it, so a step's own timeout can never extend past what remains overall. When it runs out the check fails immediately, reporting the elapsed time, the session's exit status, the plugin state, and the screen tail — a stalled session, not a slow one, and almost always a turn waiting on a permission prompt or a dialog. Shutdown is the one thing that runs after the budget: it has its own short limit and escalates to a kill.

A model-free self-check asserts the budget wins over a longer step timeout, so this cannot regress silently.

### 7.2 Environment the session must not inherit

The harness is normally run from inside a Claude Code session, which exports variables marking its children as nested sessions. Inherited, they turn the session under test into a child session with transcript saving disabled — not the ordinary session whose idle state the wake is claimed to reach. `CLAUDE_CODE_*` and `CLAUDECODE` are therefore stripped, along with `CLAUDE_PLUGIN_DATA`, which would otherwise outrank the isolated state root. `CLAUDE_CONFIG_DIR` is deliberately kept: it carries the authentication every check needs.

### 7.3 Permission prompts end the run

A permission prompt is fatal here in a way it is not in print mode. The session stops and waits, the turn never ends, no `Stop` hook fires for an unfinished turn, and the wake under test cannot happen. The harness must not answer prompts — that would mean reading the interface — so every command the scripted turns may reasonably use is allowed up front, and an unlisted one fails the run with a readable message rather than executing unreviewed.

### 7.4 The harness must say where it is

A harness that types blind produces one ambiguous failure: nothing happened, and nothing says whether the input arrived. Two facilities remove that ambiguity, and both are debugging tools rather than assertions — nothing in the harness reads them to decide anything.

**A live trace.** Every step names itself as it starts, repeats itself every five seconds while a wait is running, and reports how it ended. Deadline checks print what is left of the budget. After each turn the flattened screen is echoed, which is the only record of whether a prompt was captured as a prompt: a correction folded into the turn already running looks, in plugin state, exactly like a review that decided against proposing anything. The raw terminal stream of every run, escape sequences included, is written to `<name>.pty.log` beside the workspace, in the directory that run claimed under `test-runs/`. On by default; `WAKE_TRACE=0` silences the stdout half. `WAKE_BUDGET` overrides the per-check budget, in both directions — shorter to see a stall fail quickly, longer to find out whether a check that keeps expiring would ever have finished.

**Harness self-check.** `tests/smoke/echo_terminal.py` is a fake interactive program that echoes each captured line with a marker, redraws for a moment so quiescence has something to detect, and can emit an unprompted marker seconds later — the shape of the wake, without a model. `tests/smoke/test_echo_mode.py` drives it with the same harness the live checks use and asserts the four things they depend on: input is delivered a line at a time, turn boundaries are detected from quiescence, a marker arriving with nothing typed is seen, and one that never arrives is not. It costs nothing and is coupled to no interface, so unlike the live checks it is not marked `pty`: it is marked `harness` and runs in `make test` like any other test. `make test-harness` only reruns it alone with the trace on. The marker and the target are named for the harness rather than for the wake because that is what they exercise — nothing here touches `claude`, the plugin, the gate, or the reviewer.

Together they partition a stalled live run. If echo mode passes, the harness delivers input and detects turns, and the stall is in the session under test — which the trace then locates by step.

The cost-free checks living in the live module carry the same `harness` mark for the same reason, and the `pty` mark is applied per test rather than to the module. They drive no session: they cover the screen matcher, the budget, a session that ignores `/exit`, and the precondition that decides between skipping a run that observed nothing and failing one whose review never happened. A module-level `pty` mark kept all of that behind a paid target, where a change breaking the harness's own decision logic would not surface until someone chose to spend on a live run.

**A failing check must not wait twice.** When the candidate wait runs its full window and review stored nothing, the run does not spend a second window looking again; waiting the same interval a second time cannot change the answer, and doubling a failing check's runtime is most of what makes this harness feel like it has hung. The second wait is spent only when the first was cut short by the budget rather than by its own limit, where a late review and a missing wake are still genuinely distinguishable.

### 7.5 Only one run at a time

Both live checks used to reuse per-test workspaces under `tmp/smoke/`, wiped at the start of each test, so two concurrent runs deleted each other's state mid-flight and neither result meant anything. This happened once.

That specific collision is gone by construction: each pytest process claims `test-runs/<target>_<timestamp>/`, named to the nanosecond, and no run writes where another has written. **The rule stands anyway.** What has been removed is one way for two runs to interfere, not a demonstration that they do not — they still share `~/.claude`, the `latest` symlinks, and the account paying for both. None of that has been tested concurrently, and a harness whose failures cost a live session to reproduce is the wrong place to find out. `make wake` is still to be run alone.

What the per-run directory does buy is the thing that was actually missing: every run is still readable afterwards. `make wake-repeat` exists to measure stability across ten runs, and under the old layout it destroyed nine of them on the way to the tenth — so the run that failed, which is the only one worth reading, was the one guaranteed to be gone.

## 8. Outstanding evidence

Under the evidence rule in [`AGENTS.md`](../../AGENTS.md#specification-status) this specification stays `Implemented; unverified` until all of the following have been observed and recorded:

1. ~~`make wake` completing with both live checks passing~~ — **observed 2026-08-01.** Both checks passed in 120s together, against Claude Code 2.1.220: the wake arrived for `cand-12f3c9117d4c` carrying the lesson under test, and the control stored `cand-d5552db5fde5` and saw no wake;
2. ~~the negative control failing the run when the wake is suppressed, as its own passing assertion~~ — **observed 2026-07-31.** The control ran the full script against a `Stop` hook that discards its exit code, stored `cand-0785fcbaf540`, and reported no wake; the check passed in 91s, inside its budget;
3. ~~`make wake-repeat` completing ten consecutive runs without a failure~~ — **observed 2026-08-02.** Ten consecutive runs, no failure, each between 2m05s and 3m08s, and each in its own directory under `test-runs/` so all ten remained readable afterwards. Of the twenty checks, fifteen ran to their assertions and five skipped on a reviewer that stored no candidate; and
4. ~~a run in which the budget is *not* consumed~~ — evidence that three minutes is genuinely generous rather than the thing being measured. **Observed 2026-08-01**: the positive check completed and closed its session 32s into a 180s budget, having watched for the wake and found it rather than having waited out a timeout.

Item 4 exists because a check that always finishes at its deadline is not passing, it is timing out somewhere quiet.

### 8.1 What the first traced run showed

The trace added in section 7.4 was written to debug a run that looked like a hang. It was not one, and it named the difference on its first use:

- the scripted exchange worked. Both prompts were captured as their own turns — visible in the echoed screen — and the correcting turn ended 39s into the check, well inside every limit;
- review ran. `counters.json` recorded `count: 1` with `last_review_at` set, and the turn files were consumed;
- no candidate was stored, and no diagnostic was journalled — the shape of a reviewer that completed and returned `discard`, not of a reviewer that failed; and
- the check then spent its remaining 120s in two consecutive waits for a candidate that could no longer arrive, which is what made three minutes per check feel like a hang. Section 7.4 now forbids the second wait.

In the same run the control produced a candidate from the identical script, so the positive check's empty result is a reviewer outcome that varies rather than a broken exchange. The screen also showed the session writing its own auto-memory for the correction during the turn under test, which is a plausible reason for a reviewer to find nothing durable left to propose. That belongs to Spec-0001's gate and reviewer, not to this harness, and is recorded here only as the observation that led there.

That hypothesis was subsequently confirmed. Once Spec-0001 required every review ending without a candidate to journal its outcome, two further runs each recorded `{"stage": "review_outcome", "error_class": "no_lesson", "reason": "already_covered"}`, and the scratch project's `~/.claude/projects/<path>/memory/` held a file stating the lesson under test, written during the turn that taught it. The reviewer was correct on both runs: the lesson was already owned before its hook ran.

The harness therefore sets `CLAUDE_CODE_DISABLE_AUTO_MEMORY` on every session it launches, defaulting to `1`, overridable with `SMOKE_AUTO_MEMORY`. It is set explicitly in both directions rather than left unset, because `autoMemoryEnabled` is a user setting and an inherited value makes the check's result depend on who ran it. The wake is a claim about this plugin's hook, and it cannot be observed while another system is reaching the same conclusion first.

Setting it was not enough on its own. The harness strips every inherited `CLAUDE_CODE*` variable so the session under test is an ordinary one rather than a nested child of whatever started the harness, and that prefix rule removed the variable the harness had just set — costing a further live run that reproduced the original failure exactly. Variables the launch site sets deliberately are now named at the launch site and exempted there, rather than allowlisted in the harness: an exemption listed centrally outlives whatever needed it, and a launch site that stops setting a variable stops exempting it.

The interaction keeps a check of its own, behind `make wake-memory`, which drives the identical exchange with auto memory on and asserts coherence rather than a candidate: the reviewer either defers with `already_covered` or proposes and wakes. Failing means the two systems interfere — no review, an unreachable reviewer, or a candidate stored and never queued.

### 8.2 The exchange itself was reviewable, and was reviewed for the wrong turn

The run that followed confirmed the auto-memory fix and replaced the failure with another. No `memory/` directory existed under the scratch project, and the journalled reason changed from `already_covered` to `transient_state` — but still no candidate.

The trace and the counters together named the cause without a further run:

- `counters.json` held `count: 1`, and its `last_review_at` matched the end of the **first** turn to the second;
- the journalled outcome was six seconds later, inside that same review; and
- the correcting turn ended ten seconds after the first, against a 120-second cooldown.

The scripted exchange opens by asking the session to run the test suite. In that run `pytest` failed and a retry succeeded, which is a genuine verified-workaround signal over ordinary work, carrying no prompt into the bundle. It spent the turn's one permitted review and armed the cooldown, and the correction that followed was suppressed unreviewed. `transient_state` was the reviewer's label for a bundle that contained tool signatures and no user text; the reviewer never saw the directive at all.

This is a Spec-0001 gate defect rather than a harness one, and is fixed there: section 6 now ranks the two rate limits against the signals, and a stated directive passes a cooldown. It is recorded here because the harness's own script is what exposed it, and because the script must keep exposing it — an opening prompt that never produces incidental tool activity would make the wake check pass without exercising the ordering that broke it.

The lesson for this specification is narrower and general: a wake that does not arrive has at least four distinct causes — the exchange, the reviewer's judgement, another system reaching the conclusion first, and the gate declining to ask — and the harness alone cannot tell them apart. Each was separated by reading state the run left behind rather than by re-running it, and each fix was cheap only because the previous one had already made its own failure legible.
