# Spike 001: evaluate the Scrapeshq Claude Code Memory Plan

## Question

**Given** the implemented Hermes-style experiential-learning MVP and current official Claude Code behavior, **when** the six-part external memory plan is evaluated against the repository's privacy, mutation, portability, and evidence boundaries, **then** each part has a source-grounded `ADOPT`, `ADAPT`, `DEFER`, or `REJECT` disposition and the evidence can be checked mechanically.

Risk: **high**. The plan proposes durable capture of conversations and direct mutation of memory artifacts. A superficially convenient implementation could weaken the MVP's strongest boundaries.

## Inputs

- Preserved source capture: [`source/`](source/README.md)
- Machine-readable matrix: [`evaluation.json`](evaluation.json)
- Current normative target: [`../../docs/specs/0001-hermes-style-experiential-learning-mvp.md`](../../docs/specs/0001-hermes-style-experiential-learning-mvp.md)
- Official Claude Code documentation checked on 2026-08-04:
  - [Memory](https://code.claude.com/docs/en/memory)
  - [Hooks](https://code.claude.com/docs/en/hooks)
  - [Skills](https://code.claude.com/docs/en/skills)

The upstream Markdown and PDF are research inputs, not normative requirements.

## Method

1. Preserve the rendered landing page and original downloadable Markdown/PDF.
2. Decompose the plan into its six proposed capabilities.
3. Compare each capability with the implemented repository and current official platform documentation.
4. Require every disposition to carry repository evidence anchors.
5. Run `evaluate.py`; fail if an evidence file or anchor has drifted.

This is an architecture/evidence spike, not an implementation of the external plan. No Claude settings, memory, transcript, hook, or skill state is mutated.

## Run

From the repository root:

```bash
python3 spikes/001-scrapeshq-memory-plan-evaluation/evaluate.py
```

Expected summary:

```text
Summary: ADOPT=1, ADAPT=2, DEFER=1, REJECT=2
Evidence anchors: verified
```

## Findings

### The framing is useful; the baseline claim is stale

The plan's **store / inject / recall** decomposition is a clean way to reason about memory. Its statement that Claude Code “saves almost nothing” and “injects almost nothing” out of the box is no longer a safe premise: current official documentation describes auto memory plus CLAUDE.md, both loaded into new conversations. Any design must first inventory those supported surfaces to avoid duplicate authorities and contradictory context.

### Disposition matrix

| Capability | Result | Evaluation |
| --- | --- | --- |
| Frozen snapshot injection | **ADAPT** | Keep a bounded, next-session snapshot principle. Prefer supported CLAUDE.md/auto-memory behavior over a second project-local memory authority by default. The existing plugin's `SessionStart` hook currently surfaces deferred proposals, not broad working memory. |
| Agent-curated writes | **ADAPT** | Keep explicit retention intent, deduplication, and add/replace/remove semantics, but route writes through the implemented exact proposal and explicit authorization boundary. Direct skill-mediated edits are not acceptable for this MVP. |
| Capture every turn | **REJECT** | Exhaustive durable logs and raw transcript archives conflict with the repository's deliberate redaction and data-minimization boundary. Retain bounded event signatures and asynchronous review only. |
| Hybrid semantic search | **DEFER** | Plausible as a separate opt-in retrieval extension, but the plan lacks a retrieval benchmark, corpus/retention policy, threat model, embedding portability strategy, and measured need. It also violates the current zero-runtime-dependency constraint. |
| Source citations | **ADOPT** | Require source file, date, and heading metadata for any future recall corpus; preserve it through retrieval and return an explicit no-result outcome instead of unsupported paraphrase. |
| Full historical import | **REJECT** | A sentinel prevents duplicate execution, not privacy or scope failures. Default import of historical transcripts should not proceed without explicit opt-in, inventory/dry run, project boundaries, redaction, deletion, and re-index controls. |

### What the plan gets right

- A small bounded injection artifact is better than an unbounded junk drawer.
- Agent judgment rules should remain editable and reviewable.
- Background work should not delay completion of the user's primary task.
- Idempotency is necessary for hook-driven capture.
- Hybrid retrieval is more robust than vector-only retrieval.
- Recall should expose provenance and admit when nothing relevant was found.
- Store, inject, and recall need independent acceptance checks.

### What cannot be accepted as written

1. **“Capture everything” is not a neutral default.** It creates a sensitive behavioral archive and expands breach, retention, consent, and accidental cross-project disclosure risk.
2. **A gitignored raw transcript is still durable sensitive data.** Gitignore is not encryption, access control, retention, or deletion policy.
3. **Direct agent writes bypass the current trust boundary.** The MVP deliberately stages exact bytes, requires a user-typed authorization, backs up, verifies, and supports rollback.
4. **A vector database is an implementation choice, not proof of useful recall.** No representative query set, relevance labels, latency budget, or baseline comparison is supplied.
5. **A sentinel is not an import safety model.** It says “once,” not “with informed scope and reversible handling.”
6. **Project-local storage does not cover all Claude surfaces.** The repository explicitly forbids assuming that terminal, IDE, Desktop, web, and other surfaces share a filesystem or process.

## Recommendation for the real build

Do **not** implement the six prompts sequentially.

Use the plan to create two bounded follow-ups only:

1. Add provenance requirements to any future recall design: immutable source identifier, timestamp/date, section/heading, redaction state, and an explicit no-result contract.
2. If recall becomes a real product priority, run a separate retrieval benchmark before selecting storage: representative redacted corpus, lexical baseline, hybrid candidate, labeled queries, relevance metrics, latency, index size, deletion/re-index behavior, and cross-surface availability.

If explicit “remember/forget” UX is added, it should call the existing review/proposal lifecycle rather than write memory directly.

## Verdict: PARTIAL

### What worked

- The source artifacts were captured exactly and checksummed.
- The store/inject/recall framing exposed six independently evaluable claims.
- One element is directly adoptable, two are useful after adaptation, and the evidence checker makes drift visible.

### What didn't

- The plan is not a safe implementation specification for this repository.
- Its platform baseline is outdated relative to current auto memory.
- It provides no empirical retrieval evaluation and insufficient privacy/mutation controls.

### Surprises

- The existing MVP already implements the valuable asynchronous-review shape without accepting exhaustive transcript retention.
- The plan labels raw capture as “taken from Hermes,” while the inspected Hermes-style design in this repository emphasizes durable lessons and data minimization rather than treating every transcript as memory.

### Recommendation

Retain this as non-normative research. Adopt provenance, adapt bounded injection and curated-write UX to existing controls, reject default exhaustive capture/history import, and require a separate benchmark before semantic retrieval enters the roadmap.
