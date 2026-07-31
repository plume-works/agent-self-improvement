# Packaged smoke test

The offline suite covers everything checkable without a model. This covers what
it cannot: that the packaged plugin loads inside Claude Code, that its hooks
fire, that the reviewer prompt survives contact with a real model, and that an
applied instruction is genuinely picked up by a fresh session.

```bash
make smoke
```

That is the whole procedure. It builds its own scratch repository, isolates
plugin state, runs nine checks headlessly, and then hands you a real interactive
session for the one check that cannot be automated.

It implements [Spec-0001 section 14](specs/0001-hermes-style-experiential-learning-mvp.md#real-packaged-smoke-test)
and the [section 15 acceptance gate](specs/0001-hermes-style-experiential-learning-mvp.md#15-mvp-acceptance-gate).

## Before you run it

- **Claude Code 2.1.196 or later.** Earlier versions have no `UserPromptExpansion`
  event, which is the entire authorization path. The suite checks this and skips
  with an explanation rather than failing obscurely. Upgrade with
  `npm install -g @anthropic-ai/claude-code`.
- **Python 3.9 or later** on `PATH`, and `uv` for the test runner. The plugin
  itself installs nothing.
- **Real model usage.** Every check drives an actual session, which is why this
  is not part of `make test` or `make check`.

Nothing else. There is no directory to create and no file to seed.

## What it does not touch

The scratch repository, the plugin state, and every mutation live under
`tmp/smoke/<test-name>/`, which is gitignored. Each run wipes its own workspace
at the start and **leaves it in place afterwards**, so a failure can be opened
and read:

```bash
tmp/smoke/test_3_a_real_reviewer_produces_a_schema_valid_candidate/
├── project/          the scratch repository, with its CLAUDE.md
└── state/            candidates, proposals, backups, diagnostics.jsonl
```

`make clean` removes them.

Isolation works because `SELF_IMPROVE_STATE_DIR` outranks `CLAUDE_PLUGIN_DATA`
when the state root is resolved. Claude Code sets `CLAUDE_PLUGIN_DATA` in every
hook environment it creates and discards the inherited value, so with the other
precedence the hooks inside a real session would write to your installed plugin
data directory — mixing smoke state into your own, and letting your real
cooldown and daily review counters suppress the check.

Your own `~/.claude` is not isolated, because redirecting `CLAUDE_CONFIG_DIR`
would take the CLI's authentication with it. No check proposes a user-scope
change, and every mutation assertion checks the file it touched is inside the
scratch repository.

One thing inside `~/.claude` is removed: `projects/<scratch-path>/`, where Claude
Code keeps its own transcripts and memories for the scratch directory. Those
outlive `tmp/smoke`, so without this a second run begins already holding the
first run's memory of the lesson under test — which is how check 2 once ended in
"already saved in memory, so no update needed". The deletion is guarded on the
scratch root and can only match a smoke workspace.

## The checks

| # | Check | How |
| --- | --- | --- |
| 1 | The plugin loads and `Stop` runs after the reply | Headless, asserts on hook events |
| 2 | **The async review wakes an idle session** | **Interactive; asks you one question** |
| 3 | A real reviewer returns a schema-valid candidate | Headless, real model |
| 3b | Staging shows exact bytes; target untouched | Headless |
| 4 | Routing offers an existing owner first | Headless |
| 5a | Conversational approval authorizes nothing | Headless, real session |
| 5b | Typed authorization installs exactly those bytes | Headless |
| 6 | A fresh session picks up the instruction | Headless, real model |
| 7 | Rollback restores, and refuses over an edit | Headless |
| 10 | Nothing sensitive survives in durable state | Headless, real reviewer |

Two are worth understanding rather than just running.

**Check 5a is the security property.** It tells a real Claude that a proposal is
staged and asks it to apply it. Whatever Claude says, the assertion is on state:
the file must be unchanged, no authorization may exist, and no mutation may be
journaled. If this ever passes a change through, stop and treat it as a defect —
it is the claim the whole design rests on.

**Check 3 is the only place the reviewer prompt meets a real model.** Everything
else uses a deterministic fake. If it fails, the prompt has drifted or become
too conservative; the candidate it produced, or the reason it declined, is in
that test's `state/` directory.

## Check 2: the interactive one

A `-p` session ends its turn at `result`, so an `asyncRewake` hook has no idle
session to wake. This was measured, not assumed — see
[Spec-0002](specs/0002-pty-wake-harness.md) for the probe.

`make wake` aims to perform this check without you: it drives the same exchange
through a real interactive session on a pseudo-terminal, waits for the wake, and
verifies it against a candidate identifier it reads from disk rather than
against anything on screen. It has not yet completed a passing live run, so the
manual procedure below is still the supported way to verify the wake.

So `make smoke` pauses, prints instructions, and opens a real session in your
terminal. The scratch repository for this check gets a `Makefile` and a small
passing suite, because the correction has to be about something that really
happened: in an empty repository the request cannot be carried out, and the
session goes looking for context outside the project. You:

1. ask for the tests to be run with pytest;
2. **wait for the reply to finish** before typing anything;
3. correct it — say to always use `make test` in this repo, not pytest directly;
4. **wait up to two minutes without typing** — a line beginning
   `self-improve:` should appear on its own, naming a candidate;
5. type `/exit`; and
6. answer one yes/no question.

Three things will make it fail whatever the plugin does:

- **Typing while Claude is still working.** Text entered mid-turn is queued and
  folded into the turn already running, so it never arrives as a prompt of its
  own — `UserPromptSubmit` never sees the correction and there is nothing to
  review. This is the most common way to lose the check.
- **A pending permission prompt.** The commands the script leads to are allowed
  up front, but if Claude asks for anything else, answer it. A prompt waiting
  for you is a turn that has not ended, no `Stop` hook fires, and the wake can
  only follow a completed turn.
- **An IDE terminal.** Your editor selection is attached to every prompt there,
  so Claude can be handed the correction before you type it.

The question asked afterwards is deliberately narrow — whether a line beginning
`self-improve:` appeared on its own. Claude recalling one of its own memories, or
agreeing to use `make test`, is ordinary behaviour and not this check passing.

If you answer no, the harness prints what the state says: whether any state was
written at all, the candidates, any turn file that survived the session (each one
is a turn that never reached `Stop`), and the review counters. A missing
`counters.json` is the loudest signal there — no review ever started, so no
correction marker reached the gate.

To skip it — in CI, or when you only want the deterministic checks:

```bash
make smoke-auto
```

## If a check skips

A check that reports `SKIPPED` with `the model call did not go through` never saw
the plugin: the session was rate limited, overloaded, unauthenticated, or pointed
at a model it cannot reach. Each session is retried once, 20 seconds apart,
before the check gives up, and the skip names the class. Check 3 skips the same
way when the reviewer subprocess itself was never consulted — including the class
`other`, which is a provider failure this build cannot name yet.

Skips are not passes. Rerun once the account or the API is healthy; `make smoke`
passes `-rs`, so every reason is listed in the summary at the end.

The distinction is worth keeping intact when editing these checks. A provider
outage once produced three failures — checks 1, 3, and 6 — pointing at code that
was correct, while every check whose assertions hold for a session that never ran
reported success.

## If something fails

The failing test names its own workspace. Include:

- `claude --version` and `python3 --version`;
- `tmp/smoke/<test-name>/state/diagnostics.jsonl`, which holds bounded error
  classes and no sensitive data; and
- `./plugin/scripts/si self-test`.

Do not include a transcript. That the diagnostics file can be shared without one
is the point of keeping it to error classes.
