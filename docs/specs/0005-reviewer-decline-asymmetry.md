# Spec-0005: The reviewer declines far more often on the negative control

- **Status:** Open question; no mechanism identified. Nothing here is implemented, and nothing here blocks anything.
- **Scope:** One measured behaviour of the reviewer under the Spec-0002 harness, the hypotheses eliminated so far, and what would settle it. No design and no proposed change.
- **Discovered by:** [Spec-0002](0002-pty-wake-harness.md), verified but for its section 6.1 — its runs produced this measurement while establishing something else entirely.
- **Related:** [Spec-0004](0004-plugin-execution-tracing.md), proposed — the facility that would make this measurable, whose section 13 deliberately keeps the slices aimed at this question behind a named hypothesis.

## 0. How this was found

Spec-0002 built a pseudo-terminal harness to observe an asynchronous wake arriving at an idle session, and paired it with a negative control: the identical scripted exchange against a `Stop` hook that discards its exit code, so the wake cannot be signalled. The control exists to prove the harness can tell an absent wake from a present one.

Neither check is about the reviewer. Both simply need it to stage a candidate first, because the wake carries that candidate's identifier and the identifier is the only thing either check matches on screen. A review that declines leaves nothing to watch for, and such a run is skipped rather than failed.

The declines turned out to cluster on the control. That is visible only because both checks run the same script the same number of times, which no deliberate experiment on this had been set up to do — Spec-0002 was measuring the stability of its own harness, and got this for free. It met every criterion it set and closed; this document exists so that closing it did not mean losing what it happened to observe.

Nothing in Spec-0002 records any of the below, deliberately: a specification that has answered its own question should not be carrying someone else's.

## 1. The measurement

`make wake` drives two live checks from an identical script: the wake check, and a negative control running the same exchange against a `Stop` hook that discards its exit code. Only the wake mechanism differs, and it differs *after* the review.

The ten-run loop of 2026-08-02, twenty reviews:

| | proposed | declined |
| --- | --- | --- |
| the wake check | 9 | 1 |
| the negative control | 6 | 4 |

Four of the five declines were `transient_state`, the fifth `one_off_instruction`. Adding the three earlier live runs recorded during Spec-0002's development, the control has declined **seven** times and the wake check **once**.

A per-review decline rate high enough to produce that is also high enough to matter on its own: it is the reviewer refusing a stated, unambiguous user directive — "always use `make test` in this repo, not pytest directly" — which is the single clearest case the MVP exists to catch.

## 2. Why it is not urgent

Nothing is broken by it. A review that stores no candidate leaves the harness with no identifier to watch for and nothing to conclude about the wake, so the check skips with its journalled reason rather than failing ([Spec-0002 section 7](0002-pty-wake-harness.md#7-implementation-notes)). That is why the ten-run loop passed. The asymmetry costs observations, not correctness.

What it does cost is confidence in a number: any future claim about the reviewer's decline rate has to say which check produced it.

## 3. What has been eliminated

Both were tested against evidence already on disk or against the real reviewer. Neither needed the tracing facility of Spec-0004.

### 3.1 The gate is not the discriminator

All twenty reviews in the loop journalled `signal: explicit_retention` — both checks, declines and proposals alike. The gate reached the same conclusion by the same route every time, so nothing in `capture` or `gate` separates the two checks.

This is the cheapest possible check and it was available from `diagnostics.jsonl` and the stored candidate records, with no new instrumentation.

### 3.2 The check's own name, which the bundle carries, is not the discriminator

`candidate_owners` entries hold absolute paths, and those paths contain the name of the check that produced them:

```text
…/test_the_harness_fails_when_the_wake_does_not_arrive/project/CLAUDE.md
…/test_the_async_wake_arrives_at_an_idle_session/project/CLAUDE.md
```

Every control bundle tells the reviewer *fails*, *does not arrive*. That is the only field differing between the two checks by construction rather than by chance, and it is suggestive enough that leaving it untested would have been negligent.

Tested directly: two bundles identical in every other byte, fifteen reviews each. **No declines either way.** The name does not move the reviewer.

The design lesson outlived the hypothesis and is recorded in [Spec-0004 section 8](0004-plugin-execution-tracing.md#8-shape-without-content): the field most likely to carry a systematic difference was the one its first draft flattened hardest, to a bare count.

### 3.3 The offline replay does not reproduce the phenomenon

Across three batches, a reconstructed bundle has been replayed through the real reviewer **101 times and declined 3** — against **5 declines in 20** live reviews.

This is the most consequential of the three results, because it invalidates the cheap instrument. Any prompt change measured by offline replay has not been measured against the case that actually declines, and a synthetic run is a poor place to look for a cause. The reconstruction is faithful in every field this project can observe, which is itself evidence that whatever produces the live rate is not in the bundle as currently understood.

## 4. What has not been eliminated

- **The bundle differs in a way not yet reconstructed.** `last_assistant_message` is model prose, fresh each run; `events` may differ if the two sessions do different amounts of work. Neither has been compared between checks, because the bundle is assembled in memory and never stored.
- **Ordering or environment.** The control runs second in the same pytest process. Nothing shared has been identified — the state roots, project directories, and Claude project directories are all per-check — but "nothing identified" is not "nothing".
- **It is chance.** Seven against one is suggestive, not conclusive, and the sample is thirteen paired runs. A fair coin at the measured overall rate produces this split some of the time.

## 5. What would settle it

**Not a two-run diff.** The question is a difference in *rates*, and the fields that vary run-to-run within one check — model prose above all — will differ between checks too, for reasons that mean nothing. The wake check compared against itself is the baseline that has to come first.

What would settle it is the aggregating form in [Spec-0004 section 8.3](0004-plugin-execution-tracing.md#83-a-pair-is-the-wrong-unit-and-a-diff-alone-would-mislead): shape descriptors from many runs, grouped by check and by outcome, so that a field constant within a check and different across checks separates from one that is merely noisy. That is Spec-0004 slices T1, T4, T5, and T6.

Spec-0004 section 13 does not schedule those slices, and this specification is the reason: the two available hypotheses are spent, and a third has not been proposed. **Building the instrument before naming the question is what this pair of documents exists to avoid.**

The cheaper alternative, if the answer stops mattering: measure the rate honestly per check over enough runs to call it chance or not, and record that. Ten more runs is roughly forty minutes and a known cost.

## 6. What closing this looks like

This specification is answered when one of the following has been observed and written down:

1. a mechanism, identified and demonstrated — a named difference between the two checks' bundles or environments, shown to change the decline rate when removed;
2. a measurement large enough to attribute the split to the reviewer's own nondeterminism, with the per-check rates stated; or
3. a decision that the question is not worth the model usage, recorded as such, with the harness's skip behaviour left as the standing mitigation.

Option 3 is a legitimate outcome and should not be reached for last.
