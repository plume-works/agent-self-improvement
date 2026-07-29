# Claude Self-Improvement

A proposed Claude Code learning loop that turns verified corrections and hard-won workflows into durable, reviewable instructions and skills.

## Status

Design only. The current implementation target is a deliberately small Hermes-style experiential-learning MVP.

## MVP

> After completed work, Claude identifies a verified reusable lesson, searches for the correct existing owner, proposes one exact durable change, and applies it only after user review with backup and rollback.

The user does not write test procedures or maintain optimization datasets. Ordinary learning is grounded in explicit corrections, verified failed-then-successful approaches, completed reusable workflows, repeated friction, and direct requests to remember an approach.

See [Spec-0001: Hermes-style experiential learning MVP](docs/specs/0001-hermes-style-experiential-learning-mvp.md).

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
