# Spec-0004: Plugin execution tracing

- **Status:** Proposed; not implemented. No acceptance criterion in section 12 has been observed.
- **Scope:** A tracing facility inside `plugin/selfimprove/`, off by default, plus the reader and harness integration that make a live run analyzable afterwards.
- **Depends on:** [Spec-0001](0001-hermes-style-experiential-learning-mvp.md), implemented; [Spec-0002](0002-pty-wake-harness.md), verified but for its section 6.1.
- **Amends when implemented:** [Spec-0001 section 10](0001-hermes-style-experiential-learning-mvp.md#10-state-and-privacy) gains a fifth state class, and section 4.1 gains the environment variables of section 9 here.

## 1. Problem

[Spec-0005](0005-reviewer-decline-asymmetry.md) records a live measurement that cannot currently be explained: across the ten-run loop of 2026-08-02 plus the three earlier live runs, the negative control's review declined seven times and the wake check's declined once, on an exchange that is scripted identically for both. Four of the five declines in the loop were `transient_state`.

The reason it cannot be explained is not that the answer is subtle. It is that the plugin keeps almost nothing about a review that worked as designed. After a decline the state directory holds:

```text
counters.json                     a review happened, and when
diagnostics.jsonl                 {"stage":"review_outcome","error_class":"no_lesson",
                                   "reason":"transient_state","signal":"explicit_retention"}
```

That is the entire record. The evidence bundle that produced the decline was assembled in memory, written to the reviewer's standard input, and never stored; the turn file that fed it was deleted by `capture.discard_turn` one line later, by design, because it holds the prompt. Which signal fired is known. What the bundle around that signal actually looked like — how many events reached it, whether `last_assistant_message` arrived at all, whether the two checks even sent the same number of fields — is not recoverable, and it is precisely the difference the measurement is asking about.

### 1.1 What has already been eliminated, and with what

Two hypotheses have been tested against records that already exist, and both are dead. They are recorded here so this specification is not built to re-answer them.

**The gate is not the discriminator.** Every one of the twenty reviews in the ten-run loop — both checks, declines and proposals alike — journalled `signal: explicit_retention`. The gate reached the same conclusion by the same route every time, so nothing in `capture` or `gate` distinguishes the two checks, and slice T2 should not be expected to answer this question.

**The embedded test name is not the discriminator.** `candidate_owners` entries carry absolute paths, and those paths contain the check's own name: every control bundle tells the reviewer `…/test_the_harness_fails_when_the_wake_does_not_arrive/project/CLAUDE.md`, against `…/test_the_async_wake_arrives_at_an_idle_session/…` for the wake check. That is the only field that differs between the two checks *by construction* rather than by chance, and "fails", "does not arrive" is suggestive enough to be worth ruling out. Two bundles identical except for that name, fifteen reviews each: no declines either way.

That second result carries a warning for section 14. The same reconstructed bundle has now been replayed 101 times across three batches and declined 3 times, against 5 declines in 20 live reviews. **The offline replay does not reproduce the phenomenon at a usable rate**, so a hypothesis that cannot be settled from a live trace cannot be settled by replaying a bundle either.

The same gap shows up in four other places that have cost real time on this project:

- **The gate's silence is undifferentiated.** `orchestrate.run` returns `{"outcome": "no_signal"}` and writes nothing. A turn that was suppressed by `cooldown`, a turn that was suppressed by `candidate_awaiting_presentation`, and a turn that simply had no marker are indistinguishable afterwards, even though the first two mean *the plugin declined to look* and the third means *the plugin looked and found nothing*. Spec-0002 section 8.2 is an instance: an entire run was spent reviewing the wrong turn, and finding that out took reading a pty transcript.
- **A wake that does not arrive has no plugin-side counterpart.** The harness sees no marker on screen. Whether the hook exited 2, whether it exited 2 and Claude Code dropped it, or whether it never reached the wake at all, is not written down anywhere.
- **There is no duration anywhere.** `journal.diagnostic` stamps `int(time.time())`. Seconds cannot resolve a hook that must finish in five, and a reviewer call that took 118 seconds against a 120-second timeout looks the same as one that took two.
- **The two traces that do exist do not meet.** `tests/smoke/pty_harness.py` has a `Trace` class that narrates what the *harness* did, in the harness's clock. The plugin's diagnostics live in the state directory in a different clock at a different resolution, and correlating them is manual arithmetic on timestamps.

Each of these is the same defect: the plugin records failures and records nothing about the path that succeeded, so every question of the form *why did this run behave differently from that one* has to be answered by re-running it.

## 2. What exists today, and why it is not enough

| Facility | Covers | Missing |
| --- | --- | --- |
| `journal.diagnostic` | failure paths, plus the one `review_outcome` line added for declines | success paths, decisions, durations, any structure |
| `counters.json` | that a review ran; cooldown and daily-cap state | why the counters had the values they did |
| `store` records | candidates, proposals, authorizations that survived | everything discarded on the way |
| harness `Trace` | the terminal side of a live check | anything inside the plugin's own processes |

The `review_outcome` diagnostic added during Spec-0002's investigation is the shape this proposal generalizes. It was worth adding, it is being read in anger, and it stops one step short of useful: it says a review declined and on which signal, and cannot say what the review was looking at.

## 3. Goals

1. A live run leaves enough behind to reconstruct **what the plugin decided and why**, without re-running it and without a model call.
2. Runs can be **compared mechanically**, in groups rather than in pairs — this is what [Spec-0005](0005-reviewer-decline-asymmetry.md) needs, and comparison is a stronger requirement than readability.
3. The privacy rules of Spec-0001 section 10 hold **unchanged** at the default setting. No prompt, response, transcript body, raw tool output, full command line, or credential enters a trace.
4. Tracing **cannot break the plugin**. Every hook still fails open, still fits its timeout, and behaves identically with tracing off.
5. Off by default in an ordinary install; on for every live check in `test-runs/`.

### Non-goals

- Not a metrics or telemetry system. Nothing is aggregated, exported, or sent anywhere. The trace is a local file the user owns and can delete.
- Not a replacement for `diagnostics.jsonl`. That journal is always on and stays exactly as it is; the trace is opt-in and additive. A failure must be visible without anyone having enabled anything.
- Not a profiler. Durations are recorded because they are free at the point a span already exists, not because sub-millisecond accuracy matters.
- Not distributed tracing. There is no collector, no OTLP, no dependency. The standard-library-only constraint of Spec-0001 section 4.1 is absolute here — these are hook scripts that must fail open, and a tracing import that can fail is a tracing system that breaks the plugin it observes.

## 4. Execution model, and what it forces

The plugin has no long-lived process. Every hook is a fresh `scripts/si` invocation that reads JSON on standard input, does one thing, and exits. A single completed turn is typically five to fifteen separate processes, and the `Stop` hook's review runs in the background under `asyncRewake` while the next foreground process may already be running.

Three consequences fix the design:

1. **Spans are records, not scopes.** There is no in-process parent to attach to across a process boundary, so correlation is by explicit identifier, written into every record.
2. **Writes must be append-only and interleave-safe.** Two processes will write concurrently. `journal._append` already relies on `O_APPEND` writes under the pipe-buffer size being atomic; the trace inherits that mechanism and makes the size bound explicit rather than incidental (section 6).
3. **There is no shutdown hook to flush in.** Every record is complete when written. A span emits `span_start` and `span_end` as two independent records rather than buffering; a process killed mid-span leaves a start with no end, which is itself the most interesting thing it could leave.

### 4.1 Identifiers

| Field | Value | Source |
| --- | --- | --- |
| `run_id` | one live check or one session | `SELF_IMPROVE_RUN_ID` if set, else derived once per state root and stored in `trace/run-id` |
| `session_id` | the Claude Code session | the hook event |
| `turn_id` | the turn | `prompt_id` from the hook event, or `capture.FALLBACK_TURN` |
| `span_id` | one operation in one process | 8 random hex characters |
| `parent_span_id` | the enclosing operation | in-process only; absent at a process root |
| `pid` | the OS process | `os.getpid()` |

`run_id` is what makes the harness integration work: `make wake` exports one per check, so every record from every process of that check carries it, and a trace file that accumulated several checks can still be split cleanly. Outside a test run it is derived once and reused, so an ordinary user's trace has a stable identifier without the plugin inventing a session concept it does not have.

`turn_id` is deliberately the same identifier `capture` already uses. A trace whose turn identity disagrees with the turn file is worse than no trace.

## 5. Record schema

One JSON object per line in `trace/trace.jsonl` under the state root, sorted keys, no whitespace — the same encoding as `journal`, so the two files can be read with one parser.

```json
{"t":1785652202123456789,"run_id":"wake-01","session_id":"…","turn_id":"…",
 "span_id":"a3f1c9d2","parent_span_id":null,"pid":48213,
 "kind":"span_end","name":"orchestrate.run","dur_ms":4187,
 "attrs":{"outcome":"no_lesson","reason":"transient_state","signal":"explicit_retention"}}
```

`signal` there is the *gate's* vocabulary, which is the one `orchestrate` holds. The reviewer has a vocabulary of its own — it answers `explicit_correction` on this same turn — and the two must never be merged into one field. A trace that cannot say which component said what is a trace that has to be corroborated before it can be read.

| Field | Type | Notes |
| --- | --- | --- |
| `t` | int | `time.time_ns()`. Nanoseconds for the same reason `tests/smoke/workspaces.run_stamp` uses them: records from concurrent processes have to sort. |
| `kind` | str | one of `span_start`, `span_end`, `event`, `decision`, `shape` |
| `name` | str | dotted operation name, from a closed set (section 7) |
| `dur_ms` | int | on `span_end` only, from `time.monotonic` — never from wall time, which can step |
| `attrs` | object | bounded key/value pairs, values restricted by section 6 |
| `err` | str | on `span_end` only, an `redact.error_class` category when the span raised |

`decision` is a distinct kind rather than an attribute because it is what the trace is mostly *for*: every branch where the plugin chose not to proceed emits one, with the reason from the closed vocabulary that branch already has (`gate.suppressed`'s return values, the reviewer's `discard_reason`, the schema layer's `SchemaError.reason`). Those vocabularies exist and are already bounded; the trace does not invent parallel ones.

## 6. What may appear in `attrs`

This is the load-bearing rule of the whole proposal, so it is a whitelist rather than a prohibition. An `attrs` value must be one of:

1. a **bool**, or an **int** that is a count, size, or duration;
2. a **string from a closed set defined in the source** — a signal type, a discard reason, an error class, an outcome, a tool name, a hook event name, a decision reason;
3. an **identifier the plugin generated itself** — a candidate id, proposal id, mutation id, fingerprint;
4. a **shape descriptor** as defined in section 8.

Nothing else. Not a path, not a signature, not a marker's matched text, not a truncated anything. `redact.tool_signature` output is excluded even though it is already normalized — `Bash:pytest` is bounded and harmless, and `Edit:src/billing/customer_records.py` is a project path, and the trace layer is the wrong place to be adjudicating that case one signature at a time. The count of distinct signatures is available; the signatures are not.

A record is capped at **3500 bytes** serialized. Over that, `attrs` is replaced by `{"dropped":"oversize"}` and the record is written anyway. The cap is below `PIPE_BUF` (4096 on Linux and macOS), which is what keeps concurrent `O_APPEND` writes from interleaving — the same property `journal` depends on, stated here as a bound the code enforces rather than a property nobody checks.

## 7. Instrumentation points

The closed set of span and event names, and what each one answers.

### 7.1 Capture

| Name | Kind | `attrs` |
| --- | --- | --- |
| `capture.prompt` | span | `markers` (the marker categories, already a closed set), `prompt_kept` (bool), `prompt_len` (int), `turn_events` (int after append) |
| `capture.tool_failure` | span | `tool`, `error_class`, `turn_events` |
| `capture.tool_success` | span | `tool`, `paired` (bool), `failures_before_success` |
| `capture.discard_turn` | event | `deleted` (bool) |

`prompt_kept` and `prompt_len` are the first pair worth arguing about, so: the length of a string is not the string, a boolean saying a field was retained is not the field, and both are exactly what section 1's question needs — the two live checks differ in what the *user* typed, and if one of them is failing to reach the correction marker at all, this is the record that says so. The prompt itself remains absent from the trace at every level below section 9's content mode.

### 7.2 Gate

| Name | Kind | `attrs` |
| --- | --- | --- |
| `gate.evaluate` | span | `signal` or absent, `include_prompt`, `events_seen`, `markers_seen` |
| `gate.suppressed` | decision | `reason` (the existing closed vocabulary), `overridden` (bool, for the forced and cooldown-override paths) |
| `gate.no_signal` | decision | `events_seen`, `markers_seen`, `transitions`, `friction_max` |

`gate.no_signal` is the record that does not exist today and should. It says the gate ran to the end and found nothing, and gives the four numbers that decide every branch in `gate.evaluate`, so a turn that *nearly* fired is distinguishable from one that was never close.

### 7.3 Evidence and reviewer

| Name | Kind | `attrs` |
| --- | --- | --- |
| `evidence.build` | span | a shape descriptor of the bundle (section 8) |
| `reviewer.invoke` | span | `model`, `effort`, `timeout_s`, `payload_bytes`, `dur_ms`, `exit_code` |
| `reviewer.usage` | event | `num_turns`, `duration_api_ms`, `input_tokens`, `output_tokens`, `total_cost_usd` — read from the CLI's own JSON envelope |
| `reviewer.unavailable` | decision | `reason` (the `ReviewUnavailable` class) |
| `reviewer.schema` | decision | `reason` (the `SchemaError` reason), `response_bytes` |
| `reviewer.decision` | decision | `decision`, `discard_reason`, `confidence`, `destination_scope`, `destination_kind` |

The reviewer runs as a child process with `SELF_IMPROVE_STATE_DIR` and `CLAUDE_PLUGIN_DATA` deliberately removed from its environment, so **it cannot write to this trace**, and that stays true — it is a security property, not an oversight. Everything above is recorded by the parent from what it can observe: the argument vector it built, the wall time it measured, and the metadata fields of the response envelope it already parses. Those envelope fields are model metadata, not model output; `result` is not among them.

`reviewer.usage` is the one addition here that pays for itself outside diagnosis. `make wake` spends real money and currently reports no cost at all.

### 7.4 Orchestration, wake, and the rest

| Name | Kind | `attrs` |
| --- | --- | --- |
| `orchestrate.run` | span | `outcome`, `forced` |
| `orchestrate.duplicate` | decision | `status`, `fingerprint` |
| `orchestrate.candidate` | event | `candidate_id`, `fingerprint`, `signal` |
| `wake.signal` | event | `exit_code`, `message_bytes`, `candidate_id` |
| `hook.invoke` | span | `command` (the `si` subcommand), `event_keys` (a shape descriptor of the hook payload), `exit_code` |
| `session.start` / `session.end` | span | `pending`, `swept` |
| `mutate.apply` / `mutate.rollback` | span | `mutation_id`, `target_kind`, `bytes_before`, `bytes_after`, `verified` (bool) |

`wake.signal` is emitted immediately before `sys.exit(2)`. Its absence from a trace whose `orchestrate.candidate` is present is the exact evidence that separates *the plugin never signalled* from *the plugin signalled and the signal did not land* — the ambiguity section 1 names, resolved by one line.

`hook.invoke` wraps dispatch in `commands.main`, so every process leaves a record even when the subcommand it ran does nothing. A hook that Claude Code never called and a hook that was called and returned early are otherwise the same absence.

## 8. Shape without content

Section 3's second goal — mechanical comparison of two runs — needs the evidence bundle, and section 6 forbids the evidence bundle. The resolution is to record its **shape**: enough structure to compare two bundles for equality and to see where they differ, with nothing recoverable of what they contain.

For a mapping, the descriptor is one entry per key:

```json
{"signal":{"t":"map","n":2},
 "events":{"t":"list","n":11,"kinds":{"prompt":1,"tool_failure":6,"tool_success":4}},
 "transitions":{"t":"list","n":1},
 "last_assistant_message":{"t":"str","len":842,"h":"9c1f4e02"},
 "candidate_owners":{"t":"list","n":3,"entries":[
   {"scope":"project","kind":"CLAUDE.md","exists":true,"bytes":59,"headings_n":2},
   {"scope":"user","kind":"CLAUDE.md","exists":false},
   {"scope":"project","kind":"CLAUDE.md","exists":false}]},
 "known_fingerprints":{"t":"list","n":0},
 "user_prompt":{"t":"str","len":96,"h":"4b7a0d31"}}
```

- `t` — the JSON type. A key present with a `null` value and a key absent are different facts and stay different.
- `n` — element or member count.
- `len` — character length for strings.
- `kinds` — for the `events` list only, a histogram over the closed `kind` vocabulary, since that is the structure that actually varies between the two live checks.
- `entries` — for `candidate_owners` only, one descriptor per member, built from that member's own closed-vocabulary fields.
- `h` — a **keyed** digest of the value, 8 hex characters, described below.

The rule for what gets a digest is the rule for what gets a bare count: values from closed vocabularies are recorded as themselves, free text is recorded only as a length and a digest.

`candidate_owners` earns its per-entry descriptor rather than a bare count, and the reason generalizes. A bare `n` was the first draft, and it would have made a real difference invisible: the paths in that list embed the name of the check that produced them, which is the only part of the bundle that differs between the two live checks by construction. Section 1.1 rules that particular difference out as a *cause*, but the design lesson survives the hypothesis — **the field most likely to carry a systematic difference was the one flattened hardest**, and a shape that cannot represent a difference cannot be used to look for one. `scope`, `kind`, and `exists` are closed vocabularies, `bytes` and `headings_n` are counts, and section 6 already permits all five. The paths themselves stay out, at every level.

### 8.1 The digest must be keyed, and the key must be local

A plain `sha256` of a short free-text string is not a redaction. The candidate space for `last_assistant_message` in a scripted harness run is small enough to enumerate, and anyone holding the trace could confirm a guess.

So the digest is `hmac.new(key, value, sha256)` truncated to 8 hex characters, where the key is 32 random bytes generated on first use and stored mode 0600 at `trace/hmac-key` in the state root, **never** in the repository and never in a trace file.

This buys the property that matters and gives up nothing that was on offer: digests are comparable across runs *on the same machine and the same state root*, which is exactly the comparison Spec-0005 needs (did these checks send the same assistant message, and does it vary within a check as much as it does across them?), and a trace file shared with anyone else is a set of opaque tokens. A trace copied into `test-runs/` is comparable with its siblings because they share a state root generation; a trace pasted into an issue reveals nothing.

Truncation to 8 characters is deliberate and its consequence is stated: collisions are possible at roughly one in four billion per comparison, so a digest match is strong evidence of equality and not proof. Nothing in this design branches on a digest.

### 8.2 The comparison this is built to run

```text
$ si trace diff test-runs/wake_…/wake-arrives/state test-runs/wake_…/no-wake/state

evidence.build
  events.n                 11          11
  events.kinds             = 
  last_assistant_message   len 842     len 617      h differs
  user_prompt              len 96      len 96       h same
  candidate_owners.n       3           0            ←
reviewer.decision
  decision                 propose     discard
  discard_reason           —           transient_state
```

### 8.3 A pair is the wrong unit, and a diff alone would mislead

The open question is not *how do these two runs differ*. It is a difference in **rates** — one check declining far more often than the other across a dozen paired runs — and a two-run diff cannot tell a systematic difference from ordinary variation.

It would actively mislead. `last_assistant_message` is model prose written fresh every run, so `h differs` fires on essentially every comparison, including one wake-check run against another. A reader handed a single control-versus-wake diff would find several differing fields and no way to know which of them also differ between two runs of the *same* check.

So the reader needs an aggregating mode, and it is the mode that answers the question:

```text
$ si trace tabulate test-runs/wake-repeat-*/*/state --group-by run_label

                          wake-arrives (n=10)      no-wake (n=10)
reviewer.decision
  propose                 9                        6
  discard/transient_state 1                        3
  discard/one_off…        0                        1
evidence.build
  events.n                11 (all)                 11 (all)
  candidate_owners.n      3 (all)                  3 (all)
  last_assistant_message  len 512–903, 10 distinct len 486–871, 10 distinct
  user_prompt             len 96, 1 distinct       len 96, 1 distinct
```

Two properties matter there and neither is available from a pair: a field constant within a check and different across checks is a candidate cause, and a field that varies within a check is noise however different it looks across them. **The wake check compared against itself is the baseline**, and no control-versus-wake difference should be believed until that baseline says the field is stable.

`si trace diff` stays, for the narrow case of two runs known to differ in outcome once a candidate field is already named. It is not the deliverable.

## 9. Levels, and the content escape hatch

`SELF_IMPROVE_TRACE` selects a level. The variable is read once per process through `config`, alongside the existing settings.

| Value | Meaning |
| --- | --- |
| unset, `0`, `off` | **Default.** No trace file is opened. Every tracing call returns immediately. |
| `1`, `on` | Spans, events, and decisions. Sections 5 through 7. |
| `2`, `shape` | The above plus shape descriptors (section 8). |

### 9.1 Content mode

Diagnosing a reviewer decline may eventually need the bundle itself, not its shape. That is a legitimate need on a synthetic harness run where every byte was written by a test script, and it is flatly forbidden on a user's real session. It is therefore a separate variable rather than a third level, and it refuses unless all of the following hold:

1. `SELF_IMPROVE_TRACE_CONTENT` is set to the exact string `i-understand-this-stores-prompts`;
2. `SELF_IMPROVE_STATE_DIR` is set — content mode never writes into a state root the plugin chose for itself, which means never into `~/.claude/self-improvement`;
3. the resolved state root is not inside `paths.claude_home()`.

If any check fails, the plugin traces at the requested level and emits `trace.content_refused` with the failed condition. It does not error: refusing to store prompts must never be a reason a turn fails.

When it does engage, content goes to a **separate file**, `trace/content.jsonl`, mode 0600, and the main trace records `trace.content_enabled` at its head. A trace that was taken in content mode says so in its first line, so nobody can be handed one and not know.

`make wake` does **not** set this. It is a hand-turned dial for a person actively debugging, and section 12's acceptance includes that the harness leaves it off.

## 10. Cost and failure behavior

Tracing observes hooks that must fail open within a five-second timeout, so it inherits the strictest constraint in the plugin.

- **A tracing failure is swallowed.** Every write is wrapped; an `OSError`, a full disk, a read-only state root, or an unserializable attribute value costs the record and nothing else. There is no path by which tracing raises into a hook.
- **Off is free.** At the default level the module opens no file, generates no identifier, reads no key, and computes no shape. Shape descriptors in particular are only computed at level 2, so the mapping walk never runs at level 1.
- **Bounded on disk.** `trace/trace.jsonl` rotates to `trace/trace.1.jsonl` at 8 MB, keeping one generation. A live check produces on the order of a hundred records, so rotation is for the long-running local install that leaves tracing on, not for a test run.
- **No lock.** Appends are atomic under the size cap of section 6, and there is nothing to read-modify-write. `locking.py` is not involved.
- **The `run_id` file is best-effort.** If it cannot be written, the process uses an ephemeral one and continues; correlation degrades to `session_id` and `pid`.

## 11. Reading a trace

A new `si trace` subcommand, in `commands.py` alongside the existing ones:

| Command | Output |
| --- | --- |
| `si trace show [--run <id>] [--turn <id>]` | records in time order, one indented line each |
| `si trace turns` | one row per `turn_id`: signal, gate decision, reviewer decision, total duration, cost |
| `si trace tabulate <state>... [--group-by <attr>]` | the cross-run aggregation of section 8.3 above |
| `si trace diff <state-a> <state-b>` | the field-by-field comparison of section 8.2 |
| `si trace verify <path>` | asserts every record satisfies section 6 — the check section 12 automates |

`si trace turns` is the one to reach for first: one line per turn, saying what the gate decided, what the reviewer decided, and what it cost. Most questions end there.

### 11.1 Harness integration

`make wake` and `make smoke` set `SELF_IMPROVE_TRACE=2` and export `SELF_IMPROVE_RUN_ID` per check. Because each check already gets its own `state/` inside its own directory under `test-runs/<target>_<stamp>/` (Spec-0002 section 7.4, as amended by the per-run workspace change), the trace lands beside the pty log with no copying:

```text
test-runs/wake_2026-08-02_19-37-46.833705000/
└── test_the_async_wake_arrives_at_an_idle_session/
    ├── project/
    ├── state/
    │   ├── counters.json
    │   ├── diagnostics.jsonl
    │   └── trace/
    │       ├── hmac-key
    │       ├── run-id
    │       └── trace.jsonl
    └── wake-arrives.pty.log
```

The harness `Trace` of Spec-0002 gains one thing: it emits its own step markers with `time.time_ns()` in the same clock the plugin trace uses, so the terminal narrative and the plugin's decisions merge into one ordering by sorting on `t`. That is the whole integration — no shared process, no shared file, one shared clock.

## 12. Acceptance

Every criterion is executable and offline unless marked live. Nothing here may be marked done before it has been run and its result read ([`AGENTS.md`](../../AGENTS.md#specification-status)).

1. **Off is inert.** With `SELF_IMPROVE_TRACE` unset, a full orchestration over a fixture turn creates no `trace/` directory, and the state root is byte-identical to the same run before this spec was implemented.
2. **Every branch is recorded.** A fixture turn driven through each of: no signal, each suppressor, each signal type, reviewer unavailable (each `ReviewUnavailable` reason), schema failure, discard, duplicate, and candidate — produces a `decision` or `event` record identifying that branch. A parameterized test over the vocabularies, so a new discard reason with no instrumentation fails the suite.
3. **No content escapes.** A bundle seeded with a fake credential, an absolute path outside the project, a full shell command with arguments, and a distinctive prose sentence is driven through orchestration at level 2. None of the four appears in any file under `trace/`. Asserted on the raw bytes, not on parsed fields.
4. **`attrs` is whitelist-clean.** `si trace verify` over the trace from criterion 3 passes, and fails on a hand-written record carrying a path-shaped string.
5. **The digest is keyed and local.** Two runs sharing a state root produce equal digests for equal values; a run against a fresh state root produces different digests for the same values; the key never appears in a trace file.
6. **Concurrency is safe.** Twenty processes appending 500 records each produce 10 000 lines, every one of which parses.
7. **The size cap holds.** A span whose attributes exceed the cap is written as `{"dropped":"oversize"}` and the resulting line is under `PIPE_BUF`.
8. **Content mode refuses.** With `SELF_IMPROVE_TRACE_CONTENT` set correctly but the state root inside `paths.claude_home()`, no `content.jsonl` is created, `trace.content_refused` is recorded, and the turn completes normally.
9. **The hook budget is unaffected.** `capture-prompt` at level 2 completes within the five-second hook timeout with margin, measured over 100 invocations.
10. **A failing trace is invisible.** With `trace/` made read-only, orchestration produces its normal result and its normal `diagnostics.jsonl`.
11. **Live: a wake run is diagnosable.** `make wake` leaves a trace per check under `test-runs/`, `si trace turns` reports one row per turn with the reviewer's decision and cost, and `si trace diff` between the two checks runs and reports.
12. **Live: content mode is off in the harness.** No `content.jsonl` exists anywhere under `test-runs/` after `make wake`.

## 13. Implementation sequence

Each slice is independently useful and independently committable.

T1 through T3 are worth building for their own sake and are ordered first for that reason, not as scaffolding for the investigation.

- **Slice T1 — the writer.** `plugin/selfimprove/trace.py`: levels, identifiers, the record schema, the size cap, the swallow-everything contract, rotation. Instrument `hook.invoke` only. Criteria 1, 6, 7, 10.
- **Slice T2 — decisions.** Instrument capture, gate, orchestration, and the wake signal. Criteria 2 and 9. Justified by Spec-0002 section 8.2, which cost a run and a pty transcript to diagnose and would have been one line here. Section 1.1 rules out its answering the open asymmetry: the gate reached the same decision in all twenty observed reviews.
- **Slice T3 — the reviewer.** `reviewer.invoke` timing, envelope usage metadata, and the decision records. Adds cost reporting to every live run, which no target has today.
- **Slice T4 — shape.** The descriptor, the per-entry `candidate_owners` form, the keyed digest, `evidence.build` instrumentation. Criteria 3, 4, 5.
- **Slice T5 — the reader.** `si trace show|turns|tabulate|diff|verify`. Criterion 11.
- **Slice T6 — harness.** Makefile variables, the shared `t` clock in the pty harness, and the documentation updates of section 15. Criteria 11 and 12.
- **Slice T7 — content mode.** Last on purpose: it is the only part that can store a prompt, and it should land against a suite that already proves the default path does not. Criteria 8 and 12. Section 1.1 is a reason to doubt it will help — a synthetic bundle declines far too rarely to study — so it should be built when something concrete needs it, not on the strength of this document.

**T4 answers nothing on its own.** It records a shape no tool can yet read, so the smallest configuration that produces an answer about the asymmetry is T1 + T4 + T5 + T6, and that answer may still be "the shapes are identical" (section 14). T4 should be scheduled against a *named* hypothesis that a shape difference would confirm or kill. Section 1.1 has already spent the two such hypotheses that were available; a third has not been proposed, and inventing structure in the hope that a question forms around it is how a tracing facility turns into a second product.

## 14. What this does not answer

Stated so that no one reads [Spec-0005](0005-reviewer-decline-asymmetry.md) as solved by this document.

This proposal makes the control-versus-wake asymmetry **measurable**. It does not explain it, and it may turn out that the two bundles are identical in shape — in which case the difference is in content the trace deliberately does not keep.

The obvious next step from there would be content mode on a synthetic run, and section 1.1 is a reason to expect that not to work either: the reconstructed bundle has now been replayed 101 times and declined 3, against 5 declines in 20 live reviews. Whatever produces the live rate is not in the bundle as this project has been able to reconstruct it, so a facility that captures the bundle more faithfully may simply capture the same non-event more faithfully.

It also does not address the reviewer's nondeterminism itself. Two identical bundles may still receive different decisions; that is a property of the model, and the honest response is a decline rate measured over repeated runs, not a trace.

Everything in this section is a reason to keep T4 through T7 behind a stated question rather than building them because the design is finished.

## 15. Documentation obligations on implementation

Per [`AGENTS.md`](../../AGENTS.md#documentation-consistency), landing any slice that changes plugin behavior updates together:

- `README.md` — the develop section, for `SELF_IMPROVE_TRACE` and `si trace`;
- `docs/specs/README.md` — the status of this specification;
- `docs/specs/0001-hermes-style-experiential-learning-mvp.md` — section 4.1 for the new environment variables, section 10.1 for the fifth state class, and section 10 for the explicit statement that the trace holds no content at any default level;
- `docs/smoke-test.md` — where a trace lands in `test-runs/` and how to read it.

[`docs/specs/0005-reviewer-decline-asymmetry.md`](0005-reviewer-decline-asymmetry.md) is updated only when a trace has actually been read against it, and only with what it showed. Spec-0002 is closed and is not reopened for this.
