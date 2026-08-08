# Case study: `microsoft/SkillOpt`

- **Status:** Complete
- **Study date:** 2026-07-28
- **Source:** [`microsoft/SkillOpt`](https://github.com/microsoft/SkillOpt)
- **Pinned source commit:** [`374c832c5afc2ba314a7bf4be3343eb8e6ad63c7`](https://github.com/microsoft/SkillOpt/tree/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7)
- **Latest source release at inspection:** [`v0.2.0`](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0), commit [`e4ea6a6`](https://github.com/microsoft/SkillOpt/tree/e4ea6a6771e797ef820cdd8bfea64c57e0481065), 137 commits behind the pinned source
- **Paper inspected:** [`arXiv:2605.23904v2`](https://arxiv.org/abs/2605.23904v2), _SkillOpt: Executive Strategy for Self-Evolving Agent Skills_
- **Source license:** [MIT](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/LICENSE)
- **Related studies:** [`claude-improve`](../claude-improve/README.md), [`learning-loop`](../learning-loop/README.md), [Hermes Agent](../hermes/README.md)
- **Related design:** [Hermes-style experiential-learning MVP](../../specs/0001-hermes-style-experiential-learning-mvp.md), [hypothetical Phase 1](../../hypothetical-extensions/specs/0002-phase-1-review-only.md), [Phase 2](../../hypothetical-extensions/specs/0003-phase-2-trusted-automatic-updates.md), and [Phase 3](../../hypothetical-extensions/specs/0004-phase-3-skill-curator.md)

## Executive verdict

SkillOpt contains two materially different systems that should not be evaluated as one:

1. **The paper-oriented research trainer** is a substantial, working text-optimization framework. It rolls a fixed target model over training tasks, uses a separate optimizer model to derive structured edits, clips edits to a textual learning-rate budget, evaluates candidates on a selection split, retains the best validated skill, and evaluates that artifact on an unseen test split. Its central contribution—treating a Markdown skill as versioned external state and making every proposed change earn promotion on independent behavior—is directly relevant to Claude Self-Improvement.
2. **SkillOpt-Sleep** is a deployment-time preview that mines local coding-agent transcripts and proposes updates to `CLAUDE.md` and `SKILL.md`. It implements useful staging, protected learned regions, deterministic split assignment, local judges, evidence logs, explicit adoption, and pre-adoption backups. It does **not**, at this commit, implement all of its release and configuration claims. The ordinary harvested-session CLI is two-way train/validation by default and never scores a test set; its configured token cap is not enforced; its cross-night slow-update module is not called by the nightly cycle; its Claude `SessionEnd` marker is not consumed by that cycle; and `replay_mode="fresh"` is explicitly documented in code as unimplemented.

The paper's core train/selection/test discipline is stronger than the Sleep CLI's ordinary daily-use path. The repository itself acknowledges that its benchmark recipes and nightly CLI are separate entry points. Results from controlled benchmark harnesses therefore cannot be transferred wholesale to unattended transcript-derived self-improvement.

The most important source discrepancy is in the research path itself. Paper Section 3.6 says the epoch-wise slow update still passes through the held-out selection gate. The implementation supports that mode, but the checked-in default sets `slow_update_gate_with_selection: false`; the trainer therefore force-injects slow guidance into the **current** training skill without evaluating that slow candidate. It deliberately leaves `best_skill` untouched, so the exported best artifact remains a validation-selected snapshot unless a later ordinary candidate containing the slow field earns promotion. This is not equivalent to the paper algorithm, and the checked-in checkpoint documentation says the paper artifacts used the opt-in gated mode.

SkillOpt is nevertheless the strongest evidence in these case studies for adding a behavioral promotion gate after exact mutation review. A plausible diff and user approval answer “may this change be tried?”; a held-out replay answers the separate question “did it improve the task distribution represented by this evaluator?” Neither proves universal improvement, but the combination is much stronger than either alone.

**Recommendation:** adopt the immutable candidate artifact, bounded structured edit, train/selection/test separation, strict-improvement gate, best-known pointer, rejected-candidate evidence, and deterministic mock harness patterns. Adapt Sleep's staging and protected-region ideas into this project's typed, journaled mutation engine. Reject raw transcript bodies as durable telemetry, self-generated rubrics as an independent gate, unbounded provider calls, mutable plugin sources, direct multi-file copy promotion, and any claim that a validation gate provides rollback, privacy, or general safety by itself.

## Scope and method

This study:

1. cloned the complete upstream repository and detached it at `374c832c5afc2ba314a7bf4be3343eb8e6ad63c7`;
2. inspected all 364 tracked files, 350 reachable commits, two annotated release tags, GitHub release metadata, repository-managed workflow reality, package metadata, license, security policy, data manifests, checkpoints, tests, docs, and plugin shells;
3. traced the paper trainer from train rollouts through reflection, edit application, selection gating, slow/meta update, best-skill promotion, persistence, resume, and final unseen-test evaluation;
4. traced SkillOpt-Sleep from Claude/Codex/Cursor transcript harvest through task mining, splitting, replay, judging, consolidation, staging, adoption, state, evidence logging, scheduling, and the unused slow-update path;
5. inspected the Claude Code marketplace manifest, command, skill, hook, runner, backend, and current official Claude Code plugin, hook, and session documentation;
6. installed the pinned source in an isolated virtual environment, ran all local tests and the deterministic Sleep experiment, built source and wheel artifacts, downloaded the PyPI wheel without installing it, validated the Claude marketplace manifest, and ran shell syntax and isolated hook checks; and
7. compared observed behavior with this project's privacy, ownership, authorization, mutation, recovery, rollback, provenance, and packaged-session requirements.

No benchmark or real-backend training run was attempted. Those paths require model credentials, provider spend, and in several cases external datasets or execution environments. The paper's numerical results are reported here as **upstream measurements**, not independently reproduced facts.

## Source reality and maturity

At the pinned commit, the repository had:

| Surface                            |                        Observed reality |
| ---------------------------------- | --------------------------------------: |
| Reachable commits                  | 350, from 2026-05-21 through 2026-07-28 |
| Merge commits                      |                                      74 |
| Tracked files                      |                                     364 |
| Core `skillopt/` files / lines     |                            140 / 22,890 |
| `skillopt_sleep/` files / lines    |                              38 / 9,601 |
| Test files / lines                 |                              38 / 9,603 |
| `test_*.py` files                  |                                      36 |
| Plugin files / lines               |                              54 / 5,461 |
| Checked-in paper skills            |                                       6 |
| Release tags                       |                      `v0.1.0`, `v0.2.0` |
| Repository-controlled CI workflows |                                       0 |

The history is active and community-visible rather than a paper dump. Git history contained many authors, GitHub's contributors endpoint returned 41 contributors, and 137 commits had landed after `v0.2.0`. GitHub reported the pinned merge commit as verified. Both release tags are annotated but have no cryptographic tag signature.

The project declares itself **Alpha** in [`pyproject.toml`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/pyproject.toml#L15-L24), while the Sleep docs explicitly call that subsystem a **preview** whose interfaces and defaults may change ([`docs/sleep/README.md` lines 1–13](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/README.md#L1-L13)). Those labels match the observed pace and drift better than treating `0.2.0` as a stable product contract.

The repository is also much newer than its release identity suggests. The pinned source still declares Python package version `0.2.0`, despite being 137 commits beyond the `v0.2.0` source. A wheel built from the pinned commit is therefore named `skillopt-0.2.0` but is not the PyPI `0.2.0` wheel:

| Artifact                                                      | Files | SHA-256                                                            |
| ------------------------------------------------------------- | ----: | ------------------------------------------------------------------ |
| PyPI `skillopt-0.2.0-py3-none-any.whl`                        |   132 | `818db802507c6f82553fd24c75aa70c953ab0a712647f60e68e4595052c4b150` |
| Locally built pinned-commit `skillopt-0.2.0-py3-none-any.whl` |   189 | `122bc85bc4b678089ae25652c9943016d1110ff66aced1d5fbaaf3d90f6ecabe` |

The docs do warn that `main` contains post-release functionality ([`docs/sleep/README.md` lines 68–76](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/README.md#L68-L76)). The unresolved version collision still makes provenance and bug reports ambiguous: “SkillOpt 0.2.0” does not identify one source tree.

## What is actually implemented

### Three layers, not one loop

```mermaid
flowchart TB
    subgraph R[Paper-oriented research trainer]
      RD[Benchmark adapter + fixed splits] --> TR[Train rollouts]
      TR --> RF[Failure/success minibatch reflection]
      RF --> MG[Merge, rank, clip edits]
      MG --> MU[Apply candidate skill mutation]
      MU --> VG[Selection-set gate]
      VG -->|strictly better| BS[Current/best skill state]
      VG -->|tie or worse| RB[Rejected-step buffer]
      BS --> TS[Final unseen-test report]
      RB --> RF
    end

    subgraph S[SkillOpt-Sleep preview]
      ST[Local transcript stores or reviewed tasks file] --> HV[Harvest digest]
      HV --> MN[Heuristic or LLM task mining]
      MN --> SP[Stable train/val split by task ID]
      SP --> RP[Target replay + local/model judge]
      RP --> CO[Reflect + protected-region edits]
      CO --> SG[Validation gate]
      SG -->|accepted| DG[Staging directory]
      DG -->|explicit adopt or opt-in auto-adopt| LF[Live SKILL.md + CLAUDE.md]
    end

    subgraph C[Claude Code shell]
      CC[/skillopt-sleep command] --> WR[Bundled Bash runner]
      WR --> S
      HE[SessionEnd hook] --> MK[Append time + cwd marker]
    end
```

The research trainer and Sleep share concepts but not one implementation. Sleep vendors its own gate and defines a separate `Backend` abstraction; its module docstring calls this decoupling out ([`consolidate.py` lines 1–24](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/consolidate.py#L1-L24)). This improves standalone packaging, but duplicated contracts can drift. The slow-update and split differences below demonstrate that they already have.

## Research trainer audit

### Training, selection, and test are genuinely separate in the main path

The paper formalizes `D_train`, `D_sel`, and `D_test`: training produces candidate skills, selection chooses the best, and test is reserved for final reporting. The implementation substantially matches that design:

- train adapters or data loaders construct rollout batches;
- candidate skills are evaluated on the `valid_seen` selection split;
- [`evaluate_gate`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/evaluation/gate.py#L135-L225) accepts only `candidate_score > current_score`, rejects ties, and separately tracks the best score and step;
- each step saves the current version, history, runtime state, and `best_skill.md` ([`trainer.py` lines 1615–1629](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/engine/trainer.py#L1615-L1629)); and
- only after training does the trainer evaluate the initial, best-on-validation, and final skills on `valid_unseen` ([`trainer.py` lines 2170–2313](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/engine/trainer.py#L2170-L2313)).

This is an important distinction from many “self-improvement” systems: test outcomes do not directly select a candidate in the normal trainer control flow.

There are still limits to what “held out” means:

- train, selection, and test originate from one benchmark distribution and often one deterministic seed;
- the same selection set is queried repeatedly over many candidate steps, so optimizer development can indirectly overfit it;
- the paper reports best-on-test results for many methods and configurations, creating ordinary research-level multiple-comparison risk;
- model-based or heuristic scorers can be gamed even when samples are disjoint; and
- a positive average does not establish non-regression on safety, privacy, latency, cost, or unrelated tasks.

For Claude Self-Improvement, a held-out set must therefore be an explicit evidence class, not a “safe” boolean.

### Mutation representation is bounded and inspectable

The research path uses four concrete operations: `append`, `insert_after`, `replace`, and `delete`. The application code:

- strips protected-region markers from model-proposed content;
- blocks targets located in slow-update or appendix regions;
- applies only the first matching replacement;
- records applied, skipped, and fallback statuses; and
- inserts appends before protected tail regions ([`skill.py` lines 14–132](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/optimizer/skill.py#L14-L132)).

The edit budget is a useful semantic learning-rate analogue. It limits count, not semantic magnitude: one `replace` can still rewrite a large section, and `insert_after` falls back to append when its target is missing. Consequently, bounded edit count is not a substitute for exact byte diff limits, content-class policy, or target ownership checks.

The Sleep representation is narrower. An [`EditRecord`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/types.py#L110-L120) contains target, `add|delete|replace`, content, anchor, and rationale. It mutates only bullet lines inside a marked learned block. Normalized duplicate adds and unmatched anchors are reported rather than silently disappearing ([`memory.py` lines 73–151](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/memory.py#L73-L151)). This protected-region approach is safer than unconstrained whole-file rewriting, but line-substring delete/replace can match more broadly than intended, and there is no base hash tying the proposed edit to the reviewed file version.

### Promotion is implemented; rollback is only in-loop rejection

The research gate has three actions:

- `accept_new_best`: candidate becomes current and best;
- `accept`: candidate becomes current but the prior best remains; and
- `reject`: current and best remain unchanged.

That is a sound optimization state machine. The selection cache prevents repeat evaluation of identical skill hashes, and persisted runtime state supports resuming interrupted training ([`trainer.py` lines 867–959](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/engine/trainer.py#L867-L959)). Rejected edits and observed failure patterns are fed back into later reflection within the epoch, matching the paper's negative-feedback idea.

This is **not operational rollback**. The trainer chooses among generated artifacts; it does not deploy into a live Claude configuration and later reverse a user-visible installation. Sleep takes backups at adoption time, but has no `rollback` command, no write-ahead journal, no crash reconciliation, no stale-base check, and no post-install behavioral test.

### The slow-update default diverges from the paper

The paper says epoch-level slow guidance is generated from adjacent-epoch behavior and “still passed through the validation gate.” The implementation provides exactly that branch when `slow_update_gate_with_selection` is true ([`trainer.py` lines 1830–1918](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/engine/trainer.py#L1830-L1918)).

The default configuration instead sets:

```yaml
use_slow_update: true
slow_update_gate_with_selection: false
```

([`configs/_base_/default.yaml` lines 75–94](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/configs/_base_/default.yaml#L75-L94)). In this default mode, the trainer force-injects guidance into `current_skill` and explicitly leaves `best_skill` untouched ([`trainer.py` lines 1919–1959](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/engine/trainer.py#L1919-L1959)).

This has two implications:

1. the immediate current training trajectory can incorporate an unvalidated slow mutation; and
2. the exported best snapshot is not immediately overwritten, limiting deployment risk.

A later ordinary candidate derived from that current skill must still pass the regular selection gate before becoming best. Thus the default is less unsafe than unconditional deployment, but it is still not the paper algorithm. The checked-in checkpoint guide says paper-aligned skills used `slow_update_gate_with_selection: true` and warns that retraining with current defaults can produce a different artifact ([`ckpt/README.md` lines 72–87](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/ckpt/README.md#L72-L87)). That guide inaccurately says current `best_skill` is also written unconditionally at the boundary; the trainer source explicitly preserves it. This is concrete documentation drift in a safety-relevant setting.

## SkillOpt-Sleep audit

### Actual nightly dataflow

One stateful run does the following:

1. load Sleep state and determine the project and live skill/memory paths;
2. harvest local transcript files newer than the per-project checkpoint, with a 72-hour first-run lookback;
3. normalize each transcript to user prompts, up to five recent assistant text messages, tool names, file-history names, feedback phrases, project, branch, and timestamps;
4. mine at most a configured number of tasks using either a real backend or a deterministic heuristic fallback;
5. assign a stable train/validation split from `sha256(seed + task_id)`;
6. replay baseline validation and training tasks under the current skill/memory;
7. ask the backend to propose bounded edits, trial skill and memory edits separately, and perform a fresh final validation replay;
8. return the original documents if the final score does not strictly improve;
9. stage the report and accepted proposals; and
10. on explicit `adopt` or opt-in `--auto-adopt`, back up existing files and copy proposals to live paths.

The orchestrator is visible in [`cycle.py` lines 300–385](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/cycle.py#L300-L385) and [`cycle.py` lines 405–517](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/cycle.py#L405-L517). The final fresh replay can overturn a tentatively improved per-target edit; in that case the implementation restores original documents and reclassifies those edits as rejected ([`consolidate.py` lines 255–345](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/consolidate.py#L255-L345)). Tests cover that bookkeeping behavior.

### Train/validation/test separation exists as a helper, not as the ordinary CLI contract

[`assign_splits`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/mine.py#L222-L279) implements a defensible three-way split:

- only real tasks can enter validation or test;
- synthetic dream tasks always remain in train;
- IDs map stably across nights; and
- val/test are non-overlapping.

But the default `test_fraction` is `0.0` ([`config.py` lines 25–76](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/config.py#L25-L76)), and the ordinary `mine()` interface accepts only `holdout_fraction`, then calls `assign_splits` without any test fraction ([`mine.py` lines 287–315](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/mine.py#L287-L315)). The cycle also forwards only `holdout_fraction`, not `val_fraction` or `test_fraction` ([`cycle.py` lines 360–370](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/cycle.py#L360-L370)).

Consequently:

- the harvested-session CLI produces train and validation tasks only;
- validation is reused for every trial and the final nightly decision;
- `consolidate()` deliberately excludes any externally supplied test tasks, but the ordinary cycle never scores them; and
- benchmark experiment runners can use three-way pre-split tasks and report an external test, but that is a different entry point.

The `v0.2.0` changelog claim “3-way train/val/test split” is true of the data model and helper, not of the shipping default or ordinary harvested-session flow ([`CHANGELOG.md` lines 91–120](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/CHANGELOG.md#L91-L120)). The public Sleep docs are more careful: they say the benchmark recipe and nightly CLI are separate entry points ([`docs/sleep/RESULTS.md` lines 9–18](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/RESULTS.md#L9-L18)).

### The gate measures evaluator performance, not truth

Sleep can judge tasks through:

- exact-match and keyword-soft scores;
- local rule checks such as contains, regex, section presence, and tool-called;
- benchmark-specific local evaluators; or
- an LLM rubric judge.

A real-backend miner is asked to derive a generalized intent and a checkable criterion from the same session digest. It includes up to six truncated user prompts and one assistant final in the miner prompt, then accepts model-authored rule checks or a rubric ([`llm_miner.py` lines 30–76](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/llm_miner.py#L30-L76)).

That is useful task synthesis, but it is not an independent oracle. The same transcript evidence influences task, criterion, candidate edit, and often model judge. A candidate can improve agreement with a mistaken or incomplete rubric. The strongest evidence comes from externally defined deterministic checks or fresh user-confirmed outcomes, not self-authored rubric lift.

The mock experiment is intentionally synthetic. `MockBackend` reads hidden `rule:*` task tags, proposes their corresponding rule, and returns the exact answer if the rule is present. Its deterministic lift validates orchestration and gate rejection, not real-world model learning. The upstream code says this directly ([`backend.py` lines 127–142](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/backend.py#L127-L142)).

### Claimed nightly budget is not enforced

The built-in configuration declares `max_tokens_per_night: 400_000`, and the release changelog says Sleep supports multi-rollout reflection under a token/time budget. Repository-wide call tracing found no cycle or backend control that reads `max_tokens_per_night`. The cycle records `backend.tokens_used()` only after consolidation ([`cycle.py` lines 442–452](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/cycle.py#L442-L452)).

The current docs candidly correct the stronger impression: session/task limits “are not hard call, token, time, or monetary budgets” ([`docs/sleep/README.md` lines 123–128](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/README.md#L123-L128)). For an unattended system, a displayed but unenforced cost cap is worse than no cap because operators may assume protection that does not exist.

### Sleep's cross-night slow memory is not wired into the nightly cycle

Sleep includes:

- a `slow_memory` state property and setter;
- protected slow-field helpers; and
- `run_slow_update()`, which compares adjacent task results and asks a backend for durable guidance.

At the pinned commit, the only production-like caller is the `run_gbrain.py` experiment harness ([`run_gbrain.py` lines 90–109](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/experiments/run_gbrain.py#L90-L109)). `run_sleep_cycle()` never calls `run_slow_update`, reads `state.slow_memory`, or invokes `set_slow_memory`. The release claim that Sleep's slow update “runs even with the gate off” is therefore true of that experiment path, not the ordinary nightly cycle ([`CHANGELOG.md` lines 101–110](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/CHANGELOG.md#L101-L110)).

This matters because “nightly continual learning” otherwise means only that adopted learned blocks and archived tasks persist. There is no implemented epoch-level longitudinal guidance pass in the user-facing cycle.

## Session harvesting and privacy

### What Claude harvesting reads

The Claude harvester walks `~/.claude/projects/**.jsonl`, skipping `subagents` directories and `agent-*` files. It parses an internal transcript shape into:

- substantive user message text;
- assistant text blocks;
- tool names, but not ordinary tool arguments or results;
- up to 20 file-history snapshot names;
- project path, branch, timestamps, and raw transcript path; and
- heuristic positive/negative feedback phrases.

It filters known engine prompts, very short single-turn headless sessions, and a small set of known agent-session markers ([`harvest.py` lines 122–196](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/harvest.py#L122-L196)). It defaults to the invoked project's path relationship, a 72-hour first-run window, and bounded session/task counts. Harvest itself performs no network calls or writes, and project matching is path-based ([`harvest.py` lines 277–342](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/harvest.py#L277-L342)).

These are meaningful minimization measures. They are not a stable or complete privacy boundary:

1. Current official [Claude Code session documentation](https://code.claude.com/docs/en/sessions#where-transcripts-are-stored) says raw JSONL is internal and can change between versions. Supported hook inputs provide `transcript_path`, but the hook here does not use it.
2. User prompts and assistant text can contain credentials, client data, personal data, source code, and conceptual secrets that do not match regex patterns.
3. Claude harvesting does not redact digests before the LLM miner's outbound prompt. The miner truncates fields but sends them directly. The docs correctly state that outbound prompts are not guaranteed secret-free ([`docs/sleep/README.md` lines 29–53](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/README.md#L29-L53)).
4. The heuristic fallback stores truncated intent, follow-up constraints, attempted assistant output, branch, and session IDs in task/state/evidence paths. Redaction is pattern-based and primarily applied to diagnostics and evidence, not a semantic PII classifier.
5. `evidence.jsonl` deliberately records prompt/reply chains for observability. It is valuable for audit but becomes a second sensitive dataset requiring permissions, retention, deletion, and disclosure policy.
6. Headless and subagent exclusion is marker-based. Unknown plugins or schema changes can cause recursive self-harvesting or machine-generated tasks to enter the pool.

The reviewed tasks-file path is the best available privacy mode. A real backend refuses an externally supplied tasks file unless metadata says `"reviewed": true` ([`__main__.py` lines 152–171](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/__main__.py#L152-L171)). This is still a self-asserted boolean, not a signed review receipt or proof that the file remained unchanged after review.

### The SessionEnd hook is a marker, not harvesting or scheduling

The Claude Code hook is safe and small. It runs asynchronously on every `SessionEnd`, appends UTC time plus `$PWD` to `~/.skillopt-sleep/session-end.log`, ignores errors, and exits. It does not read a transcript, invoke a model, schedule a run, or mutate skills ([`on-session-end.sh`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/hooks/on-session-end.sh)).

The comment says the marker lets the next nightly cycle know fresh activity exists. Repository-wide reference tracing found no Sleep engine reader of `session-end.log`; only the Claude/Devin writers and a Devin hook test mention it. The cycle instead uses its own per-project last-harvest timestamp and transcript timestamps. The marker is currently inert operational telemetry.

Nightly execution is separately installed through cron or Task Scheduler by the `schedule` command. It is not triggered by SessionEnd, and the docs note that scheduler entries preserve only a subset of runtime options ([`docs/sleep/README.md` lines 130–138](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/README.md#L130-L138)).

## Claude Code integration

The integration is a valid Claude Code marketplace plugin shape:

- [marketplace manifest](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/.claude-plugin/marketplace.json);
- [plugin manifest](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/.claude-plugin/plugin.json);
- `/skillopt-sleep` [command](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/commands/skillopt-sleep.md);
- model-discoverable [skill](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/skills/skillopt-sleep/SKILL.md);
- asynchronous `SessionEnd` [hook manifest](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/hooks/hooks.json); and
- bundled runner scripts.

`claude plugin validate plugins/claude-code` passed under Claude Code `2.1.214`. Shell syntax checks passed, all scripts were executable, and the hook appended exactly one marker under an isolated temporary home.

The command gives Claude `Bash` and `Read`, then instructs it to call the bundled runner, inspect the report, and refrain from directly editing live files. It accurately warns that real backends send transcript-derived data and suggests reviewed task files ([`skillopt-sleep.md` lines 44–80](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/commands/skillopt-sleep.md#L44-L80)).

The engine is not actually bundled as a Python package inside the plugin subdirectory. The runner searches for a repository checkout, an installed `skillopt-sleep` executable, or an importable module ([`plugins/run-sleep.sh` lines 29–79](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/run-sleep.sh#L29-L79)). The PyPI wheel contains `skillopt_sleep` but no plugin files; the plugin source contains shell wrappers but depends on a checkout or separately installed Python package. Users therefore compose two independently versioned delivery channels.

There are two version/provenance problems:

1. the marketplace source tracks mutable `ref: "main"`, not a release tag or commit ([`marketplace.json` lines 17–22](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/plugins/claude-code/.claude-plugin/marketplace.json#L17-L22)); and
2. `plugin.json` remains version `0.1.0` even though the repository package and latest release are `0.2.0`, and the plugin changed in four commits after that release.

Current official [Claude Code plugin documentation](https://code.claude.com/docs/en/plugins-reference#version-management) says an explicit plugin version is the cache key and must be bumped for updates. Thus an installed plugin can remain cached at old shell assets while the user separately updates the Python engine, or vice versa.

The Claude execution backend is also not a sandbox boundary. It invokes `claude -p` in a temporary directory with permission mode `dontAsk`, loads `user,project` setting sources by default, and uses the user's installed CLI and authentication ([`claude_backend.py` lines 17–24](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/model/claude_backend.py#L17-L24), [`claude_backend.py` lines 244–294](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt/model/claude_backend.py#L244-L294)). Temporary working directories reduce accidental project mutation; they do not prove network isolation, tool isolation, extension isolation, or secret-free prompts.

## Staging, adoption, backup, and rollback

Sleep's default review boundary is directionally good:

- a run writes `proposed_SKILL.md`, `proposed_CLAUDE.md`, `report.json`, `report.md`, and `manifest.json` into a project staging directory;
- live files do not change unless `adopt` runs or `auto_adopt` is explicitly enabled; and
- adoption copies pre-existing live files into `staging/backup/` before overwriting them ([`staging.py` lines 272–342](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/skillopt_sleep/staging.py#L272-L342)).

This is reviewable staging plus backup, not a recoverable mutation protocol:

- the manifest records target paths and booleans but no proposal hash, base hash, owner, mode, source evidence hash, review identity, or expiry;
- `adopt` trusts mutable manifest paths and proposal files at execution time;
- it does not verify that `accepted` is true;
- it does not reject symlinks or paths that changed since staging;
- backup and copy are ordinary `shutil.copy2` operations rather than temporary-file, fsync, rename, and directory-sync steps;
- skill and memory are copied sequentially, so a second-file failure leaves partial adoption;
- backup filenames use only basenames and can collide for unusual target pairs;
- no receipt records resulting hashes;
- no post-write structural or fresh-session validation runs; and
- there is no rollback CLI or automatic recovery from a partial operation.

Claude Self-Improvement should retain the UX but route adoption through its journaled mutation state machine. A staged candidate should be immutable by hash; approval should bind exact bytes and all paths; recovery material must be durable before the first live write; and rollback should be an executable, tested operation rather than “a backup exists somewhere.”

## Claims versus observed evidence

| Upstream claim                                         | Observed implementation                                                                                                                    | Assessment                                                                                 |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Skill is the trainable state; model weights stay fixed | Trainer injects evolving Markdown while using configured target/optimizer models                                                           | Implemented                                                                                |
| Candidate edits are bounded and structured             | Four research operations with edit-count budget; three protected-block Sleep operations                                                    | Implemented, but count does not bound semantic size                                        |
| Candidate edits pass a held-out gate                   | Ordinary research steps and Sleep val trials use strict improvement                                                                        | Implemented for those paths                                                                |
| Train, selection, and test are separate                | Main trainer uses all three; Sleep helper supports three; harvested CLI defaults to train/val and does not score test                      | True for paper trainer, overstated for ordinary Sleep                                      |
| Test is locked until final report                      | Main trainer evaluates `valid_unseen` after training                                                                                       | Implemented in normal research control flow                                                |
| Every slow-update candidate is selection-gated         | Supported opt-in; current default force-injects into current training skill                                                                | False for checked-in default; paper checkpoints used opt-in mode                           |
| Rejected edits become negative feedback                | Research trainer keeps an epoch-local buffer; Sleep reports rejected edits but does not carry an equivalent optimizer buffer across nights | Implemented in research path, partial in Sleep                                             |
| `best_skill.md` is compact and portable                | Six Markdown checkpoints are checked in; adapter/harness still determines behavior                                                         | Artifact exists; portability is empirical and conditional                                  |
| SkillOpt is best or tied-best on all 52 paper cells    | Paper and README report this; six skills and split manifests are present                                                                   | Upstream result, not independently reproduced from committed logs                          |
| Sleep reviews sessions “offline”                       | Harvest is local; real mining/replay/judging/reflection call configured providers                                                          | “Offline” means outside normal turns, not offline from network/provider                    |
| Sleep defaults are safe and bounded                    | Review-gated adoption and project/task limits exist                                                                                        | Partly true; no hard token/time/money cap, no transaction, regex-only redaction            |
| `max_tokens_per_night` caps spend                      | Config value exists; no cycle enforcement call was found                                                                                   | Not implemented                                                                            |
| Sleep cross-night slow update runs even gate-off       | Module and experiment caller exist; ordinary cycle does not call it                                                                        | Not implemented in user-facing nightly cycle                                               |
| Three-way Sleep split                                  | Helper and task schema exist; ordinary mining omits test fraction, default is zero                                                         | Capability exists; shipping default/flow is two-way                                        |
| Fresh-worktree replay                                  | `replay_mode` default comment says fresh-worktree replay is not implemented                                                                | Not implemented                                                                            |
| SessionEnd hook signals fresh data to the next cycle   | Hook appends a marker; cycle has no reader                                                                                                 | Marker implemented, integration absent                                                     |
| Nothing live changes before adoption                   | Ordinary run stages; only explicit adopt or opt-in auto-adopt writes live                                                                  | Implemented                                                                                |
| Adoption backs up first                                | Existing live files copied to staging backup                                                                                               | Implemented, but no rollback/recovery protocol                                             |
| Harvest is private/read-only                           | File scan itself is read-only and scoped                                                                                                   | Local read is implemented; real backend egress and evidence retention remain privacy risks |
| Known secrets are redacted                             | Broad regex redactor covers many credential forms in evidence/diagnostics                                                                  | Defense in depth, not a confidentiality guarantee                                          |
| Claude Code integration is shipped                     | Valid plugin shell exists                                                                                                                  | Implemented shell; engine is a separate checkout/package and versions drift                |
| PyPI `0.2.0` represents current source                 | Pinned source still calls itself `0.2.0` but builds a materially different wheel                                                           | False as an identity guarantee                                                             |
| Tests/CI validate the project                          | Large local suite exists; no tracked repository workflow runs it                                                                           | Tests are real; CI enforcement absent                                                      |

## Paper results and reproducibility limits

The paper reports:

- six benchmarks;
- seven target models;
- direct chat, Codex, and Claude Code harnesses;
- best or tied-best on 52/52 measured cells;
- GPT-5.5 average gains of +23.5 points direct, +24.8 Codex, and +19.1 Claude Code; and
- positive cross-model, cross-harness, and cross-benchmark transfer.

The repository provides meaningful reproduction inputs:

- trainer, adapters, prompts, and configurations;
- deterministic split manifests for six benchmarks;
- six GPT-5.5 optimized skill documents; and
- an evaluation-only CLI.

[`ckpt/README.md`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/ckpt/README.md#L1-L70) also states the limitations: most upstream benchmark payloads still need external materialization, and only the first artifact batch is present. The repository does not contain raw per-cell trajectories, model response logs, token/cost ledgers, full baseline artifacts, all 52 optimized checkpoints, or a machine-readable table from which the headline can be regenerated without substantial provider and dataset setup.

The Sleep results are more candid than the top-level headline. [`docs/sleep/RESULTS.md`](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/docs/sleep/RESULTS.md#L139-L186) reports:

- single-seed primary cells;
- a catastrophic ungated `−52.8` point stress case;
- an 18-cell diverse-rollout-plus-recall mean of only `+0.53` points;
- seven of 18 cells below `−0.5` even in that experiment configuration; and
- a three-seed spot check whose outcomes ranged from `−1.9` to `+4.7`.

Those measurements support two modest conclusions: bad textual updates can catastrophically steer obedient models, and validation gating can reject some of them. They do not establish that nightly transcript mining generally improves a user agent, that the gate catches every harmful mutation, or that the default CLI reproduces the benchmark configuration.

## License and supply-chain audit

### Positive evidence

- The repository has a clear [MIT license](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/LICENSE).
- It includes Microsoft's standard [security reporting policy](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/SECURITY.md).
- GitHub reports the pinned commit's signature verification as valid.
- PyPI publishes both wheel and source distribution for `0.1.0` and `0.2.0`.
- The built wheel excludes repository plugins, avoiding an accidental claim that those shell integrations are installed by pip.
- `pyproject.toml` defines explicit package discovery and Markdown package data.

### Residual risks

- Runtime dependencies use minimum bounds only; there is no lockfile or constraints file. A future `pip install skillopt` can resolve a different OpenAI, Azure, HTTP, YAML, NumPy, or workbook stack ([`pyproject.toml` lines 26–57](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/pyproject.toml#L26-L57)).
- Build dependencies are also unpinned (`setuptools>=68.0`, `wheel`).
- No SBOM, provenance attestation, signed release asset, or independently signed checksum is published.
- Annotated tags are unsigned even though the pinned commit is GitHub-verified.
- The source version collision permits different `0.2.0` wheels from PyPI and current source.
- Plugin marketplace installation tracks mutable `main` while explicit plugin version `0.1.0` can suppress updates.
- Plugin and Python engine are distributed separately and can become incompatible.
- There is no repository-controlled release workflow tying tests to the tag or PyPI publication.
- The top-level WebUI defaults to `0.0.0.0`, which exposes it on all interfaces unless the user chooses localhost; the README at least warns about that ([`README.md` lines 85–101](https://github.com/microsoft/SkillOpt/blob/374c832c5afc2ba314a7bf4be3343eb8e6ad63c7/README.md#L85-L101)).

The correct integration posture is to pin a reviewed commit or released artifact by hash, resolve and record dependencies, and never install the mutable marketplace source or a source-built `0.2.0` under the assumption that it equals PyPI `0.2.0`.

## Test and CI reality

### Local checks at the pinned commit

| Check                                               | Result                                                     |
| --------------------------------------------------- | ---------------------------------------------------------- |
| Editable install with development dependencies      | Passed                                                     |
| `pytest -q -rs`                                     | **557 passed, 6 skipped** in 20.70 s                       |
| Deterministic researcher experiment                 | Passed; mock held-out `0.3333 → 1.0`, harmful edit blocked |
| `python -m skillopt_sleep --help`                   | Passed                                                     |
| Isolated `status --json`                            | Passed; zero-night empty state                             |
| `claude plugin validate plugins/claude-code`        | Passed under Claude Code `2.1.214`                         |
| Claude plugin Bash syntax                           | Passed                                                     |
| Isolated SessionEnd hook                            | Passed; one marker, exit 0                                 |
| Source distribution and wheel build                 | Passed, with setuptools license deprecation warnings       |
| PyPI wheel download/inventory                       | Passed; 132 files, Sleep included, plugins absent          |
| `ruff check .`                                      | **Failed: 181 findings**                                   |
| `ruff check skillopt skillopt_sleep skillopt_webui` | **Failed: 122 findings** (`51 I001`, `46 F401`, others)    |

The six test skips were explicit:

- optional Gradio absent;
- optional `json_repair` absent for three tests;
- no-engine fallback impossible while the package is importable; and
- `gbrain-evals` data absent.

The suite is substantial and directly tests many important mechanics: gates, scheduler behavior, split leakage, unmatched edits, final rollback bookkeeping, secret redaction, handoff behavior, runner fallback, plugin synchronization, backend isolation, JSON parsing, and platform paths. Passing it is strong evidence that those deterministic units work at this commit.

There is no tracked `.github/workflows/` directory. GitHub's API reported dynamic Microsoft/GitHub-managed CodeQL, dependency-graph, Copilot, and Pages workflows, but no repository-defined workflow that installs the package and runs the 557-test suite, lint, builds, plugin validation, or artifact smoke tests. The 181 lint findings confirm that the declared Ruff configuration is not an enforced green gate.

The tests also do not independently validate:

- paper model scores;
- real provider spend caps;
- real transcript privacy across schema versions;
- live Claude/Codex/Cursor permission boundaries;
- interrupted multi-file adoption recovery;
- a rollback command;
- source/PyPI/plugin version compatibility; or
- fresh packaged Claude Code discovery and invocation of an adopted skill.

## Strengths worth retaining

### 1. Behavior earns promotion

SkillOpt's best idea is not “let an LLM rewrite a prompt.” It is “materialize a candidate, run it against independent scored tasks, and promote only strict improvements.” Claude Self-Improvement should add this after exact review for destinations where a deterministic or independently reviewed evaluator exists.

### 2. The best-known artifact is separate from the current experiment

Tracking current and best independently permits exploration without losing the best validated snapshot. This should become immutable candidate IDs plus an atomic active-pointer promotion, not repeated overwrites of one live file.

### 3. Textual learning rate makes semantic drift visible

A small edit budget encourages inspectable transitions and supports attribution. The target project should augment it with byte/section limits, protected ownership regions, forbidden content classes, and exact base hashes.

### 4. Rejections are data

Rejected patches, score deltas, failure patterns, and unmatched edits are useful evidence. They should remain structured and queryable without automatically becoming model instructions or permanent memory.

### 5. Test split remains reporting-only in the main trainer

This is the right experimental discipline. Claude Self-Improvement should distinguish:

- evidence used to author a candidate;
- validation used to authorize promotion;
- test used for periodic unbiased reporting; and
- canary/production outcomes used to detect later drift.

### 6. Staging and protected learned regions improve reviewability

Sleep does not rewrite arbitrary human prose during proposal generation. It writes a clearly marked learned block and stages exact candidate files. That is a useful compatibility design for agent-owned sections, though human-authored files still require exact review and journaled mutation.

### 7. Observability covers the complete decision chain

Per-task details, raw reflection, call error, token count, accepted/rejected/unmatched edits, and gate formula make a stalled run diagnosable. The target project should preserve the chain while storing references, hashes, scores, and redacted summaries rather than transcript or prompt bodies.

### 8. Deterministic mock backends make state-machine tests cheap

The mock experiment is not evidence of agent lift, but it is an excellent acceptance-test pattern for candidate generation, rejection, staging, and promotion invariants.

## Risks and failure modes

### Validation overfitting and evaluator gaming

Repeatedly selecting against a small fixed validation set turns it into training information. Self-authored rubrics amplify the problem. Rotate or quarantine test sets, cap candidate queries, preserve untouched periodic test suites, and use deterministic external checks where possible.

### Scope confusion between research and deployment

A benchmark trainer with curated tasks and gold evaluators is not equivalent to mining arbitrary user sessions. Documentation and telemetry must identify which path produced a claim.

### Privacy is broader than secret regexes

Client names, unpublished designs, personal history, and proprietary logic are sensitive even when no token-shaped credential exists. The target repository's rule not to store prompts, responses, or transcript bodies is the stronger default.

### Backups without recovery create false confidence

A copied preimage helps a human recover manually, but it does not establish atomicity, crash safety, stale-write protection, or a successful rollback. Recovery has to be a tested state machine.

### Model and evaluator are not independent by default

Using one provider/model family to mine tasks, generate edits, attempt tasks, and judge answers creates correlated error and reward-hacking channels. Separate roles and prefer mechanical checks.

### Unenforced configuration is misleading

A token cap or replay mode must either be enforced and tested or rejected at configuration load. Silent no-op safety settings are unacceptable.

### Mutable delivery erodes auditability

A mutable `main` plugin, stale cache version, minimum-only dependencies, and duplicate package version mean the reviewed source may not be what executes.

## Comparison with Claude Self-Improvement

Claude Self-Improvement's specifications are proposed; this table compares designs, not two completed products.

| Concern            | SkillOpt research trainer       | SkillOpt-Sleep                            | Claude Self-Improvement design implication                              |
| ------------------ | ------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------- |
| Intake             | Curated benchmark tasks         | Raw transcript digests or tasks file      | Keep explicit, minimal evidence envelopes                               |
| Candidate          | Versioned skill text            | Staged skill/memory learned blocks        | Use immutable typed candidate + exact patch                             |
| Authoring evidence | Training split                  | Mined train tasks                         | Never let validation/test content enter authoring                       |
| Promotion          | Strict selection improvement    | Strict val improvement, then review/adopt | Require authorization **and** behavior gate where feasible              |
| Reporting          | Unseen final test               | No ordinary CLI test report               | Add quarantined periodic test and canary outcomes                       |
| Mutation           | Research output directory       | Sequential live file copies               | Use journaled, hashed, recoverable mutation engine                      |
| Best state         | `best_skill.md`                 | Latest staged proposal                    | Use immutable artifact store + active pointer                           |
| Rollback           | Rejection to prior current/best | Backup only                               | Provide tested rollback and crash reconciliation                        |
| Ownership          | One optimizer-owned skill       | Learned region inside human files         | Preserve human/platform/agent ownership classes                         |
| Privacy            | Benchmark data                  | User/assistant transcript text            | Do not persist or export transcript bodies by default                   |
| Provenance         | Step/history files              | Reports, evidence JSONL, session IDs      | Store hashes and minimal normalized evidence references                 |
| Cost               | Token summary                   | Token count recorded; cap unenforced      | Hard preflight and runtime budgets with fail-closed behavior            |
| Integration        | Adapters and CLI harnesses      | Thin Claude plugin + separate engine      | Ship one pinned, checksummed compatibility set                          |
| CI                 | Local tests only                | Same suite                                | Require repository-controlled cross-platform CI and package smoke tests |

## Adopt, adapt, reject

### Adopt

- explicit train/selection/test roles;
- strict-improvement candidate promotion;
- separate current and best-known state;
- immutable skill versions and score records;
- bounded structured edits;
- protected engine-owned regions;
- rejected and unmatched edit bookkeeping;
- deterministic task IDs and split assignment;
- final fresh validation replay before staging;
- local deterministic judges for checkable tasks;
- review-before-adopt as the default;
- complete but privacy-minimized decision telemetry; and
- deterministic mock backends for state-machine acceptance tests.

### Adapt

- turn `best_skill.md` into a content-addressed candidate artifact plus atomic active pointer;
- bind every gate result to model, harness, evaluator, task-manifest, code, dependency, and candidate hashes;
- combine edit-count budget with exact diff, byte, section, and content-class limits;
- treat a gate pass as evidence scoped to one evaluator and distribution, not universal safety;
- require deterministic external checks or separately reviewed rubrics before automatic promotion;
- use rolling validation plus quarantined test suites and post-promotion canaries;
- carry rejected edits as structured evidence with retention limits, not prompt-growing prose;
- preserve Sleep's learned-block concept only for explicitly engine-owned regions;
- replace raw transcript walking with supported hook/export/SDK seams and a versioned fallback adapter;
- make provider egress opt-in per evidence source and display exact outbound fields;
- convert evidence logs to hashes, counts, score components, and bounded redacted summaries;
- make every configured budget or isolation mode executable and fail closed if unavailable;
- replace staging copy with write-ahead journal, durable preimage, stale-base checks, atomic per-file installation, reconciliation, and tested rollback; and
- ship plugin and engine as one compatibility matrix with immutable source and artifact hashes.

### Reject

- calling provider-backed replay “offline” without qualification;
- broad automatic transcript harvesting as a Phase 1 default;
- raw prompt, response, or transcript bodies in durable telemetry;
- self-authored rubrics as the sole independent promotion gate;
- two-way validation results presented as unseen test improvement;
- unvalidated slow updates in a paper-aligned default;
- unenforced token/time/money or isolation settings;
- mutable `main` marketplace sources;
- stale explicit plugin versions;
- source builds that reuse a released package version for different contents;
- direct sequential overwrite of multiple live files;
- backup-only “rollback” claims;
- automatic writes to Claude-managed auto-memory; and
- benchmark headline results generalized to a user's nightly agent without matched evidence.

## Concrete implications for this repository

1. **Add a behavioral gate only after the Phase 1 exact-review core works.** SkillOpt validates a later phase, not a reason to widen the first release.
2. **Define four evidence partitions in the schema:** authoring/train, promotion/validation, periodic test, and post-promotion canary. A task ID may belong to only one pre-deployment partition for a given experiment version.
3. **Make every evaluation manifest immutable.** Record task hashes, split algorithm and seed, evaluator version, target model, optimizer model, harness, tool policy, environment, candidate hash, and retry/sampling settings.
4. **Scope every conclusion.** Store “improved `12/15` on evaluator X at revision Y,” never “safe” or “better” without qualifiers.
5. **Preserve exact candidate lineage.** Candidate records need parent ID, edit list, authoring evidence IDs, rejected siblings, validation result, and promotion receipt.
6. **Keep best-known state as a pointer.** Do not mutate the only copy of a skill during experimentation. Promote an immutable artifact atomically after authorization and validation.
7. **Separate authorization from quality.** Human exact approval authorizes a mutation; validation supplies outcome evidence. Neither silently substitutes for the other.
8. **Require a fresh final replay.** Do not rely only on cached or per-edit trial scores before promotion.
9. **Do not expose hidden safety knobs.** The engine must reject unsupported `fresh-worktree`, token-cap, or rollback configurations rather than accept and ignore them.
10. **Never use validation tasks to write the patch.** This includes model prompts, error summaries, rubrics, and manual debugging output.
11. **Quarantine evaluator authoring.** A rubric derived from the same transcript as the candidate is proposal evidence, not independent validation, until separately reviewed or mechanically grounded.
12. **Add candidate-query budgets.** Fixed validation sets leak through repeated scores; cap trials and reserve untouched periodic tests.
13. **Create adversarial evaluator fixtures.** Include reward hacking, formatting-only gains, privacy regressions, malicious transcript instructions, empty/missing anchors, contradictory edits, and candidates that improve average score while failing a critical task.
14. **Preserve the no-transcript-telemetry invariant.** Keep counts, timestamps, content hashes, source classes, and bounded redacted rationale; do not copy user or assistant bodies into evidence logs.
15. **Treat hook-provided transcript paths as locators, not consent.** Apply source allowlists, sensitive-project exclusions, schema adapters, minimization, and an explicit egress decision.
16. **Make rollback executable.** Test interrupted two-file installs, stale bases, symlinks, disk-full behavior, permission failures, and idempotent reconciliation.
17. **Add provenance to packaged integration.** Plugin manifest, native engine, schemas, and compatibility metadata must identify one release and source commit; package smoke tests must run what users install.
18. **Run a shadow phase before automatic promotion.** Collect candidate/gate evidence without writes, calibrate false acceptance/rejection, and publish the evaluator's limitations.
19. **Keep human-authored artifacts review-only.** Automatic validation can strengthen evidence, but it does not grant ownership or mutation authority.
20. **Use SkillOpt's negative result honestly.** The `−52.8` ungated collapse is a release-gate fixture: any future automatic updater must demonstrate that a harmful proposal is rejected and the live artifact remains byte-identical.

## Final assessment

SkillOpt provides unusually concrete evidence that natural-language procedures can be treated as external, versioned, testable program state. The research trainer implements most of the paper's central loop, including the part this project most needs: a candidate does not become the best artifact merely because an optimizer model explains it persuasively.

The audit also shows why “validation-gated” is not a complete self-improvement architecture. The quality of the result depends on task construction, split integrity, evaluator independence, query count, model/harness stability, privacy boundaries, provider behavior, artifact provenance, mutation atomicity, and rollback. SkillOpt-Sleep implements pieces of that operational envelope but leaves material claims unwired or experimental at the pinned commit.

The right synthesis for Claude Self-Improvement is:

> Treat every learned instruction as an immutable candidate with explicit lineage. Let a deterministic policy decide whether it may be tried, let exact review decide whether human-owned bytes may change, let an independently specified held-out evaluator decide whether promotion evidence is positive, and let a journaled mutation engine make the change recoverably. Never turn one gate score into a claim of universal safety or improvement.
