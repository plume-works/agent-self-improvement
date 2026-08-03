# Claude Self-Improvement

A Claude Code learning loop that turns verified corrections and hard-won workflows into durable, reviewable instructions and skills.

## Status

All four slices of [Spec-0001](docs/specs/0001-hermes-style-experiential-learning-mvp.md) are in `plugin/`, with an offline suite covering the ten acceptance conditions of its section 15, and a [packaged smoke test](docs/smoke-test.md) that drives a real Claude Code session.

The offline suite passes, and nine of the ten smoke checks pass. The tenth — an asynchronous review waking an idle session — cannot be observed in print mode, where a turn ends at `result` and there is no idle session to wake. The pseudo-terminal harness of [Spec-0002](docs/specs/0002-pty-wake-harness.md) automates it behind `make wake`. Both of its live checks were observed passing together (2026-08-01) — a wake arrived at an idle session, and a suppressed wake was detected as absent — and `make wake-repeat` then completed ten consecutive runs with no failure (2026-08-02). Five of those twenty checks skipped rather than asserting, because the reviewer stored no candidate and a run with nothing staged observes nothing about the wake. One of the five was a wake check, so nine of the ten runs — not ten — actually watched a wake arrive, which is why that spec's stability criterion is recorded as partially verified. Four of the five were the negative control, an asymmetry carried as an open question in [Spec-0005](docs/specs/0005-reviewer-decline-asymmetry.md).

Codex is not currently supported. [Spec-0003](docs/specs/0003-codex-integration.md) maps every Claude-specific integration point to Codex and proposes a dual-host package. It records the current parity gaps explicitly: no documented asynchronous idle-session wake, command-expansion event, generic tool-failure event, no-tools reviewer switch, or behavioral equivalent of Claude's path-scoped Markdown rules.

A live run currently records its failures and almost nothing about the path that worked, so questions of the form *why did this run behave differently from that one* can only be answered by running it again. [Spec-0004](docs/specs/0004-plugin-execution-tracing.md) proposes an opt-in trace inside the plugin — what each hook decided and why, what the review cost, and the evidence bundle as a keyed *shape* rather than its content, so two runs can be diffed. It is not implemented, it is off by default, and content never enters it outside a separately gated mode the harness does not use.

The plugin runs on Python 3.9 or later using the standard library only. Nothing is installed, no virtual environment is built, and no network access is needed at runtime — the hook scripts that must fail open have no bootstrap step to fail in. Development tooling is managed with `uv` and is not a runtime dependency.

## Install

Requires Claude Code **2.1.196 or later**; earlier versions have no `UserPromptExpansion` event, which is the entire authorization path.

Try it in one session without installing anything:

```bash
claude --plugin-dir /path/to/agent-self-improvement/plugin
```

To keep it across sessions, install it from the marketplace this repository publishes at its root. From inside Claude Code:

```text
/plugin marketplace add /path/to/agent-self-improvement
/plugin install self-improve@agent-self-improvement
/reload-plugins
```

The marketplace may also be added by its remote, `plume-works/agent-self-improvement`, in which case Claude Code fetches the plugin itself and no local clone is needed.

### Refreshing a local install

Installing **copies** the plugin into Claude Code's own cache under `~/.claude/plugins/cache/agent-self-improvement/self-improve/<version>/`, so editing this repository or pulling new commits changes nothing about the installed plugin until it is refreshed. Refresh the marketplace first, then reinstall:

```bash
claude plugin marketplace update agent-self-improvement
claude plugin install self-improve@agent-self-improvement
claude plugin details self-improve@agent-self-improvement
```

The reinstall re-copies the cache and re-stamps `gitCommitSha` in `~/.claude/plugins/installed_plugins.json` to the commit checked out here — the fastest way to confirm which revision is actually loaded.

`claude plugin update` was observed to leave `gitCommitSha` and the cache untouched when only files outside `plugin/` had changed. Whether it re-copies when `plugin/` itself changes under an unchanged `version` has not been tested here; reinstall is the reliable path until it is.

For iterating on the plugin, prefer `--plugin-dir` over any of this. It loads `plugin/` in place, with no cache copy and no reinstall between edits.

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
make wake-memory # how the wake interacts with Claude's own auto memory
make test-harness # self-check the pty harness alone; already part of make test
make wake-repeat # ten consecutive wake runs, to measure its stability
```

The sessions `make smoke` and `make wake` drive run on `sonnet` at `low` effort, overridable with `SMOKE_MODEL` and `SMOKE_EFFORT`; setting either to empty restores your CLI's own default, which is what a suspected model- or effort-specific failure has to be reproduced against. They only follow a written procedure, so neither dial changes what the checks observe, and an unconfigured run should not bill Opus at the default `high` effort to find that out.

Every driving session also runs with Claude Code's own auto memory disabled, and `CLAUDE_CODE_DISABLE_AUTO_MEMORY` is set explicitly rather than inherited. Auto memory records the lesson these checks drive *during the turn that teaches it*, before this plugin's `Stop` hook runs, so the reviewer finds it already owned and correctly declines — right behavior that reads as a broken wake. `SMOKE_AUTO_MEMORY=1` turns it back on, and `make wake-memory` is the check that deliberately does so: it asserts the two systems defer to each other rather than interfere. See [docs/smoke-test.md](docs/smoke-test.md#auto-memory).

The reviewer *under test* has its own dials — `SELF_IMPROVE_REVIEW_MODEL` (`sonnet`) and `SELF_IMPROVE_REVIEW_EFFORT` (`medium`) — and the harness deliberately leaves them alone. Its prompt meeting the configuration that ships is the point of the exercise.

Every live run gets a directory of its own — `test-runs/<target>_<timestamp>/` — holding one scratch workspace per check, its isolated plugin state, and the raw terminal stream of each pty session. Nothing is ever overwritten: `make smoke` and `make wake` cannot land in each other's directory, and the ten runs of `make wake-repeat` are ten readable results rather than one, which matters when the loop stops at the third. `test-runs/latest` and `test-runs/latest-<target>` point at the newest of each. `make clean` removes them all, and `make clean-claude` removes what they leave in `~/.claude/projects/`, outside where `clean` can reach.

`make wake` traces itself as it goes — every step, a heartbeat every five seconds while it waits, and the screen after each turn — so a stalled run says where it stalled while it is still stalling. `WAKE_TRACE=0` silences it; `WAKE_BUDGET=<seconds>` overrides the per-check budget. When a live run stalls, `make test-harness` says which half to suspect: it drives the same harness against a fake terminal that only echoes what it captured, so if it passes, input is being delivered and the stall is in the session under test. It tests the harness rather than the plugin, costs nothing, and is an ordinary part of `make test` — the target just reruns it alone with the trace on.

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
- [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins)
- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex `AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## License

Licensed under the [MIT License](LICENSE).
