# Claude Self-Improvement

A Claude Code learning loop that turns verified corrections and hard-won workflows into durable, reviewable instructions and skills.

## Status

All four slices of [Spec-0001](docs/specs/0001-hermes-style-experiential-learning-mvp.md) are in `plugin/`, with an offline suite covering the ten acceptance conditions of its section 15, and a [packaged smoke test](docs/smoke-test.md) that drives a real Claude Code session.

The offline suite passes, and nine of the ten smoke checks pass. The tenth — an asynchronous review waking an idle session — cannot be observed in print mode, where a turn ends at `result` and there is no idle session to wake. The pseudo-terminal harness of [Spec-0002](docs/specs/0002-pty-wake-harness.md) automates it behind `make wake`. Its negative control passes — a suppressed wake is detected — but the positive check has not yet passed, so an arriving wake is currently evidenced only by the interactive question in `make smoke`.

The plugin runs on Python 3.9 or later using the standard library only. Nothing is installed, no virtual environment is built, and no network access is needed at runtime — the hook scripts that must fail open have no bootstrap step to fail in. Development tooling is managed with `uv` and is not a runtime dependency.

## Install

Requires Claude Code **2.1.196 or later**; earlier versions have no `UserPromptExpansion` event, which is the entire authorization path.

Try it in one session without installing anything:

```bash
claude --plugin-dir /path/to/claude-self-improvement/plugin
```

Check the install invariants at any time:

```bash
./plugin/scripts/si self-test
```

## Use

Most of the time there is nothing to do. After a turn that produced a real correction, a verified workaround, or repeated friction, the session wakes on its own with one candidate and Claude presents an exact proposal.

| Command | Effect |
| --- | --- |
| `/self-improve:improve` | Force a review of the current turn when automatic detection missed something |
| `/self-improve:apply <proposal-id> <hash-prefix>` | Install exactly the displayed bytes |
| `/self-improve:reject <proposal-id>` | Discard the proposal; the target is untouched |
| `/self-improve:rollback <mutation-id>` | Restore the verified backup |

Only a command **you type** authorizes a change. Claude invoking the same skill, or you saying "looks good", produces no authorization and the mutation refuses.

To turn it off without uninstalling, set `SELF_IMPROVE_DISABLE=1`.

## Develop

```bash
make test        # offline suite, no model calls
make lint        # ruff
make validate    # claude plugin validate ./plugin
make check       # the three above
make smoke       # packaged smoke test against a real session; spends model usage
make smoke-auto  # the same, skipping the one interactive check
make wake        # the asynchronous wake, verified automatically on a pty
make wake-echo   # the same harness against a fake terminal; no model, no cost
make wake-repeat # ten consecutive wake runs, to measure its stability
```

`make smoke` and `make wake` leave their scratch workspaces under `tmp/smoke/` so a failure can be opened and read, along with the raw terminal stream of each pty run.

`make wake` traces itself as it goes — every step, a heartbeat every five seconds while it waits, and the screen after each turn — so a stalled run says where it stalled while it is still stalling. `WAKE_TRACE=0` silences it; `WAKE_BUDGET=<seconds>` overrides the per-check budget. When a live run stalls, `make wake-echo` says which half to suspect: it drives the same harness against a fake terminal that only echoes what it captured, so if it passes, input is being delivered and the stall is in the session under test.

`make wake` is opt-in and gates nothing. It spends model usage on two real reviews, and it is the one component here coupled to a terminal interface with no compatibility contract. Each of its checks is bounded to three minutes and run **one at a time** — two concurrent runs share the same scratch workspaces and destroy each other's results.

## MVP

> After completed work, Claude identifies a verified reusable lesson, searches for the correct existing owner, proposes one exact durable change, and applies it only after user review with backup and rollback.

The user does not write test procedures or maintain optimization datasets. Ordinary learning is grounded in explicit corrections, verified failed-then-successful approaches, completed reusable workflows, repeated friction, and direct requests to remember an approach.

See [Spec-0001: Hook-driven experiential learning plugin MVP](docs/specs/0001-hermes-style-experiential-learning-mvp.md).

### Hook-driven architecture

```text
UserPromptSubmit / tool outcome hooks
→ deterministic meaningful-event gate
→ asynchronous Stop-hook review in an independent Claude context
→ wake the original session only for one durable candidate
→ exact proposal with explicit apply/reject commands
→ atomic mutation, fresh-session verification, and rollback
```

The existing `claude-improve` reasoning workflow is narrowed into a noninteractive current-turn reviewer; its broad history scan and direct multi-artifact mutation are not inherited. Anthropic's official [`security-guidance`](https://code.claude.com/docs/en/security-guidance#how-the-plugin-integrates-with-claude-code) plugin demonstrates the same supported Stop hook → independent background review → session wake pattern.

The reviewer is a separate `claude -p` call with a reviewer-only system prompt, hooks disabled, and no tools at all. It receives its evidence on standard input, so it has nothing to read, write, or execute with. It cannot mutate an artifact even if it tries.

### What a proposal may touch

| Scope | Allowed targets |
| --- | --- |
| User | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md`, `~/.claude/skills/<name>/SKILL.md` |
| Project | `./CLAUDE.md`, `./.claude/CLAUDE.md`, `./.claude/rules/*.md`, `./.claude/skills/<name>/SKILL.md` |

Nothing else. Settings, hook configuration, Claude-managed auto-memory, and source files are rejected before any I/O, as are symlinks and paths that resolve outside an allowed root.

### MVP principles

- Finish the user's task before learning review.
- Evidence before persistence.
- Discard temporary task state and unverified guesses.
- Search and patch the existing owner before creating a skill.
- Let the model propose; let the user authorize.
- Apply only exact reviewed bytes.
- Back up, verify, and support rollback.
- Do not persist raw transcripts, prompts, responses, or credentials.
- Do not require behavioral test suites for ordinary experiential learning.

## Hypothetical extensions

The previous multi-phase architecture has been retained without rewrite under [`docs/hypothetical-extensions/specs/`](docs/hypothetical-extensions/specs/README.md). It is research material, not an MVP dependency or release plan.

Prompt optimization, automatic skill evaluation, unattended mutation, curator automation, additional Claude surfaces, daemons, retrieval systems, and federation all remain hypothetical extensions.

## Case studies

See [`docs/case-study/README.md`](docs/case-study/README.md):

- [Hermes Agent](docs/case-study/hermes/README.md) — the closest model for experiential reflection, artifact routing, ownership-aware persistence, and recoverable curation
- [`aviadr1/claude-meta`](docs/case-study/claude-meta/README.md) — a minimal explicit reflection baseline
- [Self-improving Claude Code bootstrap seed](docs/case-study/bootstrap-seed/README.md) — triage and pressure-driven structure without a trusted mutation boundary
- [`TerenceBristol/claude-improve`](docs/case-study/claude-improve/README.md) — useful manual reflection and placement UX with overly broad model-mediated mutation
- [`robinslange/learning-loop`](docs/case-study/learning-loop/README.md) — a broad knowledge system whose operational scope exceeds the MVP

## Authoritative platform documentation

- [Claude Code plugins](https://code.claude.com/docs/en/plugins)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Skills](https://code.claude.com/docs/en/skills)
- [Memory](https://code.claude.com/docs/en/memory)

## License

Licensed under the [MIT License](LICENSE).
