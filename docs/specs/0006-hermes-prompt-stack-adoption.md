# Spec-0006: Hermes-derived prompt stack adoption

- **Status:** Proposed; research and design only. No runtime prompt change or acceptance result has been observed.
- **Scope:** Improve the Claude MVP's candidate recall, classification, and owner routing by adapting the prompt stack inspected in Hermes Agent `aec3318`, while retaining Spec-0001's bounded evidence, one-candidate limit, no-tools reviewer, exact proposal, explicit authorization, and rollback.
- **Depends on:** [Spec-0001](0001-hermes-style-experiential-learning-mvp.md), implemented; its privacy and mutation invariants remain authoritative.
- **Related:** [Spec-0005](0005-reviewer-decline-asymmetry.md), an open live-review finding this change must not claim to resolve without live evidence.
- **Research basis:** [Hermes prompt deep dive and attached corpus](../case-study/hermes/README.md#attached-prompt-corpus).
- **Amends when implemented:** Spec-0001 sections 7, 8, and 14, plus the shipped reviewer prompt and `improve` skill. Until the acceptance evidence in section 13 here is observed, Spec-0001 and the current prompt remain the accepted behavior.

## 1. Problem

The MVP has a strong control plane and a weakly calibrated reasoning layer.

The deterministic gate already limits review to a named high-signal event, but
`plugin/reviewer/prompt.md` tells the downstream model that discarding is correct “most of
the time.” `plugin/skills/improve/SKILL.md` repeats that a no-lesson result is “the most
common” outcome. The same lesson is therefore screened twice with different priors:

```text
deterministic gate: this turn has a supported learning signal
        |
        v
review prompt: assume there is probably nothing to learn
```

This is not merely theoretical. Spec-0005 records live reviews declining the direct user
instruction “always use `make test` in this repo, not pytest directly.” It does not identify
the prompt as the cause, and offline replay does not reproduce the live rate, so this
specification does not claim causality. It does establish that the current reasoning policy
has insufficient observed recall on the clearest positive case.

The current prompt also splits closely related policy across two agents without making the
handoff explicit:

- the no-tools reviewer decides whether there is a lesson and emits only an `owner_query`;
- the foreground `improve` skill searches and reads exact owners, drafts bytes, and stages a
  proposal.

Hermes makes that split work through a layered prompt: foreground policy, a live skill
index, a detailed background-review message, model-visible mutation schemas, and
deterministic write guards. The MVP has the guards but has adopted only part of the
reasoning rubric.

One concrete implementation mismatch was found during this research. The shipped
`improve` skill says its third routing option is “add or patch a linked reference,” while
`selfimprove/allowlist.py` accepts only a skill's root `SKILL.md`, not files under
`references/`. The wording advertises an action the staging boundary refuses. This spec
does not widen the mutation surface; it makes the prompt capability-accurate as described
in section 8.

## 2. Goal

Adopt the parts of Hermes's prompt stack that improve judgment:

1. active treatment of real corrections after a signal has already fired;
2. user-natural examples of corrections and frustration;
3. a clear fact/preference/procedure distinction;
4. loaded-owner and existing-umbrella routing before creation;
5. a class-level name veto against one-session skills;
6. explicit rejection of transient state, negative capability claims, and unresolved
   failures;
7. authoring guidance close to the staging action; and
8. behavioral evaluation that measures both recall and over-capture.

The result should reduce false declines on explicit durable instructions without increasing
unsafe or low-value proposals.

### Non-goals

- Do not give the reviewer tools, filesystem access, transcript access, or mutation power.
- Do not copy Hermes's direct background writes, user-profile store, `MEMORY.md`, periodic
  curator, usage telemetry, or archive lifecycle into this change.
- Do not make “five tool calls” proof that a skill should exist. Tool count is a scheduling
  hint, not learning evidence.
- Do not add multi-file proposals or widen the allowlist to skill support files here.
- Do not make ordinary users author behavioral test suites. Evaluation fixtures are
  repository-owned, redacted acceptance artifacts.
- Do not claim that prompt wording alone resolves Spec-0005's live asymmetry.

## 3. Invariants retained from Spec-0001

Every implementation slice must preserve all of the following:

1. deterministic classification runs before model review;
2. the reviewer sees one bounded, redacted evidence bundle for one completed turn;
3. the reviewer has no tools and cannot read or mutate an artifact;
4. malformed, policy-violating, unsupported, and low-confidence output becomes a discard;
5. at most one candidate emerges from one review;
6. the foreground agent reads an exact owner before drafting any change;
7. the staged proposal contains exact bytes and an exact diff;
8. no durable write occurs without the existing one-time literal authorization;
9. the mutator retains path, symlink, stale-preimage, backup, verification, journal, and
   rollback protections; and
10. prompts, responses, transcript bodies, credentials, and raw tool output never enter
    telemetry.

An active reviewer prior changes whether a candidate is proposed. It grants no authority to
apply one.

## 4. Adoption map

The upstream corpus is evidence, not a drop-in runtime dependency.

| Hermes prompt mechanic                                                           | Decision for this plugin                                             | Reason                                                                                                                                              |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| “Be ACTIVE” and do not default to `Nothing to save.`                             | **Adapt** to reviews whose deterministic gate already named a signal | Hermes reviews run periodically over broad conversations; this plugin has a stronger pre-filter and can calibrate by signal type.                   |
| Natural correction phrases and frustration as first-class signals                | **Adopt**                                                            | Users rarely write a formal retention request or rationale.                                                                                         |
| User facts in `USER.md`, environment facts in `MEMORY.md`, procedures in skills  | **Adapt** to user/project `CLAUDE.md`, rules, and skills             | The MVP must not mutate Claude-managed memory and has no plugin-owned fact store.                                                                   |
| Loaded skill → existing umbrella → support file → new umbrella                   | **Adopt first, second, and fourth; defer support-file mutation**     | Current staging permits `SKILL.md` but not package subfiles or atomic two-file link updates.                                                        |
| Class-level names; veto PR/error/codename/task names                             | **Adopt**                                                            | Prevents narrow skill proliferation.                                                                                                                |
| Environment failures, negative tool claims, transient errors, one-off narratives | **Adopt**                                                            | These become stale self-imposed constraints.                                                                                                        |
| Reject unresolved failures dressed as reliable workflows                         | **Adopt**                                                            | Persisted instructions must be grounded in an observed success or explicit user directive.                                                          |
| Patch a loaded skill immediately                                                 | **Adapt** to one exact proposal                                      | The foreground agent may recommend and stage; only the user-authorized mutator writes.                                                              |
| Protected skills are off-limits to autonomous review                             | **Strengthen through architecture**                                  | This reviewer cannot write any skill. Human-authored targets remain review-only and may receive an exact proposal for the user to accept or reject. |
| Memory tool's atomic batch grammar                                               | **Do not copy**                                                      | The MVP emits one candidate and one proposal; it has no memory batch.                                                                               |
| Skill tool's trigger/steps/pitfalls/verification authoring rubric                | **Adopt** in the `improve` skill                                     | This policy belongs beside exact-byte drafting and staging.                                                                                         |
| Mandatory load of every partially relevant skill                                 | **Do not copy globally**                                             | A self-improvement plugin does not own Claude's behavior on unrelated turns. Loaded-owner preference remains local to proposal routing.             |
| Curator umbrella-building prompt                                                 | **Use as design evidence only**                                      | Library-wide consolidation is outside this slice and has materially different permissions and recovery requirements.                                |

## 5. Reviewer calibration

The reviewer prompt must state that the input reached it because the deterministic gate
found a named signal. It must actively adjudicate that signal rather than applying one
blanket prior to all evidence.

### 5.1 Signal-specific prior

| Signal                | Review stance                                                                                                            | Required evidence                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `explicit_retention`  | Presume the user's stated standing instruction is proposal-worthy; look for a one-off or contradiction before discarding | The user's own words and durable applicability. No successful command is required for a preference or standing rule. |
| `explicit_correction` | Presume a durable replacement is proposal-worthy when it corrects future behavior                                        | The corrected behavior must be stated, not inferred from silence. Do not invent a rationale.                         |
| `confirmed_technique` | Actively extract the narrow reusable technique                                                                           | Explicit confirmation plus enough bounded evidence to know what worked.                                              |
| `verified_workaround` | Propose only the verified recovery pattern, never the original failure                                                   | A compatible failure-to-success transition.                                                                          |
| `repeated_friction`   | Treat repetition as a reason to inspect, not a lesson                                                                    | A verified remedy or explicit durable user instruction; otherwise discard.                                           |
| `reusable_completion` | Look for a class-level procedure, not a narrative of this task                                                           | Verified outputs and a procedure applicable beyond the exact file or issue.                                          |
| `manual_force`        | No positive or negative presumption                                                                                      | Apply the ordinary durability, verification, and ownership tests.                                                    |

“Most reviews should discard” and “most reviews should update” are both forbidden as global
instructions. The prior is determined by the named signal.

### 5.2 Directives do not need invented evidence

A terse instruction using “always,” “never,” “don't,” “only,” or a flat replacement such
as “use uv, not pip” is stated evidence. The reviewer must not require:

- a reason the user did not give;
- a second correction;
- an explicit request to remember;
- a successful tool call for a communication or workflow preference; or
- agreement from the assistant's final message.

The proposed lesson contains the behavior only. It must not manufacture a benefit,
technical explanation, or causal claim.

### 5.3 Preferences about answers are in scope

The current prompt excludes a preference “about the answer rather than the work,” which
conflicts with Hermes's treatment of style, format, legibility, tone, and verbosity as
first-class learning signals.

The replacement policy is narrower and durable:

- a stable cross-task communication preference routes to user `CLAUDE.md`;
- a project-specific output convention routes to project `CLAUDE.md` or an existing rule;
- a format or workflow specific to a class of task routes to its existing skill when one
  owns the class; and
- a one-off request for this answer only is discarded.

One review still produces one candidate. It does not duplicate the same preference into
both a standing instruction and a skill.

## 6. Learning classification

Before choosing propose or discard, the prompt makes the reviewer classify the candidate
internally as one of four shapes:

| Shape                  | Meaning                                                       | Preferred destination                                        |
| ---------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ |
| `user_preference`      | Stable way this person wants Claude to communicate or work    | User `CLAUDE.md`, unless limited to a task class             |
| `project_convention`   | Stable fact or rule true of this repository                   | Project `CLAUDE.md` or a scoped rule                         |
| `procedure`            | Multi-step method for a recurring class of work               | Existing skill, then a new class-level skill only if unowned |
| `technique_or_pitfall` | A verified step, recovery, or trap within a broader procedure | Existing owner, usually a skill or rule                      |

The classification need not be added to persistent output in the first slice. It is a
reasoning step that makes destination selection consistent. If later exposed in the schema,
it must be a bounded enum and must not become free-form telemetry.

## 7. Negative learning policy

The reviewer must discard all of the following unless the user explicitly stated a durable
instruction that survives the negative event:

1. missing binaries, credentials, packages, or fresh-install state;
2. a version, branch, issue, PR, commit, file count, or completed-work status likely to be
   false within seven days;
3. claims that a tool or feature “does not work” based on one environment or session;
4. a transient failure resolved by retry when no reusable retry policy was established;
5. an unresolved sequence of failed attempts presented as a recommended workflow;
6. common practice whose inverse is obviously incompetent;
7. a one-off instruction about the current branch, file, output, or run;
8. a narrative whose identity is today's task rather than a class of tasks; and
9. a preference inferred from silence or mere acceptance of one suggestion.

If setup state caused failure and a verified fix was observed, the candidate is the setup or
recovery instruction—not the negative capability claim.

The schema adds bounded discard labels `environment_dependent`, `negative_capability_claim`,
and `unresolved_failure`. They are diagnostic categories only; no explanatory model prose is
journaled.

## 8. Owner routing and capability truth

The no-tools reviewer continues to emit `owner_query`, not a target path. Exact owner
selection remains in the foreground `improve` skill, where files can be read.

The skill must choose in this order:

1. patch an artifact already loaded or used in the session when it owns the topic;
2. patch an existing class-level `CLAUDE.md`, rule, or skill owner;
3. patch the owning skill's `SKILL.md` with a concise subsection for a technique or pitfall;
4. create a new class-level skill only when no existing artifact owns the class; or
5. use a short standing instruction when the lesson is not a procedure.

The current linked-reference step is removed until a separate implementation provides all
of the following together:

- an allowlisted support-file path grammar;
- exact preview of both a new support file and the `SKILL.md` link that discovers it;
- one authorization hash over the complete multi-file change set;
- all-or-nothing application, verification, journal, and rollback; and
- package-integrity checks for relative links and existing support files.

Until then, the prompt must not tell Claude it can stage a support-file change. Recognizing
that detail would ideally become a reference is useful analysis; claiming the current
mutator can write it is not.

### 8.1 Class-level creation veto

A new skill proposal is invalid when its name or trigger is tied to:

- a PR or issue number;
- an exact error message;
- a branch, feature codename, or current phase;
- one library name without a reusable task class;
- “fix-X,” “debug-Y,” “audit-Z,” or equivalent session wording; or
- a procedure that makes sense only for today's artifact.

The `improve` skill must fall back to an existing owner or a standing instruction. It must
not evade the veto by inventing a broader name around narrow content.

## 9. Prompt placement

Hermes repeats policy at the system, review, and tool layers. This plugin has different
surfaces, so the adopted content is divided by responsibility.

### 9.1 `plugin/reviewer/prompt.md`

Owns:

- capability and strict JSON contract;
- gate-aware signal calibration;
- natural-language correction examples;
- durability, verification, and negative-learning tests;
- learning-shape and destination classification;
- class-level name veto;
- privacy; and
- one-candidate behavior.

It must not contain staging commands, mutation instructions, or claims that it can inspect
files.

### 9.2 `plugin/skills/improve/SKILL.md`

Owns:

- retrieving a candidate;
- loaded-owner and umbrella-first search order;
- reading the exact target;
- minimal-diff drafting;
- skill authoring quality: trigger conditions, numbered steps where procedural, exact
  commands only when evidenced, pitfalls, and verification;
- capability-accurate supported destinations; and
- exact staging and presentation commands.

It must say “propose” and “stage,” never “save,” “patch immediately,” or another verb that
implies the foreground model itself may mutate the destination.

### 9.3 `plugin/reviewer/schema.json`

Retains the current propose fields and strict validation. It adds only the bounded discard
labels from section 7 unless a measured evaluation demonstrates that a new structured field
is necessary. Schema expansion is not a substitute for better reasoning.

## 10. Prompt-source maintenance

The [attached Hermes corpus](../case-study/hermes/prompts/README.md) is a pinned research
snapshot, not vendored runtime code. Runtime prompts are maintained in this repository and
may diverge where the architectures differ.

Each implementation PR must include a clause-level review table in its description:

```text
upstream clause | adopted wording/location | adaptation reason | enforcement counterpart
```

This prevents an attractive phrase from being copied without its required capability or
guard. It also makes intentional divergence distinguishable from prompt drift.

Structural tests must pin concepts and contracts, not arbitrary prose. Tests may assert that
the prompt names unresolved failures, the loaded-owner preference, and the JSON-only output
contract; they must not make harmless wording edits impossible.

## 11. Evaluation corpus

Add synthetic, redacted fixtures under `tests/prompt_eval/`. No fixture may be copied from a
live Claude transcript or contain authentication state. Each fixture contains:

- a bounded evidence bundle in the exact production shape;
- expected `propose` or `discard`;
- allowed signal type;
- allowed scopes and destination kinds for a proposal;
- forbidden invented claims;
- an existing-owner expectation where routing is under test; and
- a short reason written by the repository author, not sent to the model.

The minimum corpus covers:

1. explicit project retention;
2. terse workflow correction;
3. stable user communication preference;
4. task-class-specific format preference;
5. verified workaround;
6. confirmed technique;
7. reusable multi-step completion;
8. repeated friction with no remedy;
9. unresolved failures;
10. environment-dependent setup state;
11. transient retry;
12. negative tool claim;
13. common practice;
14. one-off instruction;
15. inferred preference;
16. existing loaded owner;
17. existing umbrella but no loaded owner;
18. narrow new-skill name temptation; and
19. genuine unowned class-level skill.

Fixtures test policy, not phrasing. More than one output can be valid where scope or owner is
genuinely ambiguous; allowed sets make that explicit.

## 12. Evaluation method

### 12.1 Free deterministic checks

The ordinary offline suite must verify:

- the prompt and schema still enforce one JSON object;
- every propose field and enum is synchronized between prompt, schema, and validator;
- every discard label is bounded and journal-safe;
- the reviewer command still has no tools, hooks, MCP servers, or filesystem access;
- the `improve` skill advertises only allowlisted destinations;
- a new-skill name passes the existing strict path grammar;
- malformed or low-confidence output is a discard; and
- no runtime or fixture imports a non-standard-library dependency into the plugin.

These checks prove wiring and safety, not model quality.

### 12.2 Opt-in model evaluation

Add `make prompt-eval`; it spends real model usage and is never part of `make test` or
`make check`. For each fixture it runs the current baseline prompt and the candidate prompt
against the same model, effort, and evidence bytes. Order is alternated so one variant does
not always run first.

Every report records:

- prompt SHA-256;
- schema SHA-256;
- model identifier and effort;
- fixture identifier;
- variant and run order;
- parsed decision and bounded discard label;
- contract validity; and
- aggregate rates only—never reconstructed prompts or transcript bodies.

Raw model output lives only in the opt-in test-run directory with mode `0600` and is not
committed. Repository fixtures themselves are synthetic and may be committed.

Run at least three repetitions per fixture per variant. This is a minimum for catching gross
regressions, not a statistical proof.

### 12.3 Live review check

Offline replay did not reproduce Spec-0005's live decline rate. Before rollout, drive at
least ten fresh Claude sessions through the packaged hook path with the canonical explicit
retention instruction and ten with a negative control containing no durable instruction.

The check must observe whether a candidate was actually stored; a started, skipped,
timed-out, or interrupted review is not evidence. `make wake` output must still be captured
to a file because it costs real money, but the prompt check should have its own target and
result directory so wake transport and reviewer judgment are not conflated.

## 13. Acceptance criteria

No item is complete until its command ran and its output was read in the same evidence
session.

### 13.1 Implementation

- [ ] The reviewer prompt implements sections 5 through 7 without granting tools or writes.
- [ ] The `improve` skill implements the routing and authoring policy in sections 8 and 9.
- [ ] Prompt, schema, validator, and journal agree on every discard category.
- [ ] The false linked-reference capability is removed from shipped guidance.
- [ ] Synthetic redacted evaluation fixtures cover every case in section 11.
- [ ] README, Spec-0001, and the spec index are updated together as required by `AGENTS.md`.

### 13.2 Safety and wiring

- [ ] `make test` passes with no unexpected skip.
- [ ] `make lint` passes.
- [ ] `make validate` passes or reports only the repository's documented missing/old-CLI skip.
- [ ] Tests observe that the reviewer has no tools and that proposals remain inert without a
      literal one-time authorization.
- [ ] Tests observe that support-file paths are rejected while the feature is deferred.

### 13.3 Model quality

Using one recorded model/effort pair and at least three repetitions per fixture:

- [ ] explicit retention and explicit correction proposal recall is at least 95%;
- [ ] no unresolved-failure, negative-capability, environment-state, or inferred-preference
      fixture produces an accepted proposal;
- [ ] verified-workaround and confirmed-technique recall is at least 85%;
- [ ] existing-owner cases choose a compatible owner query and never recommend a new narrow
      skill;
- [ ] valid JSON/schema rate is at least 99%; and
- [ ] compared with the baseline prompt, the candidate does not increase the negative-fixture
      proposal rate and either improves explicit-signal recall or already reaches the 95% floor.

### 13.4 Packaged live behavior

- [ ] Ten fresh packaged sessions with the canonical explicit retention case each store one
      valid candidate.
- [ ] Ten fresh packaged negative-control sessions store no candidate.
- [ ] The existing packaged smoke and wake requirements still pass; their transport evidence
      is reported separately from prompt-judgment evidence.

If model-quality or live criteria fail, the implementation status is **Implemented;
unverified** or **Implemented; quality gate failed**, with the observed rates in the status
line. Written code, prompt inspection, and offline structural tests are not enough to call
the prompt improvement complete.

## 14. Rollout and rollback

The prompt change ships only after section 13 passes. The implementation PR retains the
baseline prompt in test fixtures long enough to reproduce the comparison, but runtime has
one prompt—no silent per-user randomization and no telemetry experiment.

Rollback is a code revert of the prompt, schema labels, and `improve` skill wording. Candidate
and proposal record formats remain compatible because this spec does not add required
persistent fields. Candidates created by either prompt continue through the same approval,
mutation, and rollback path.

## 15. Expected result

The desired reviewer is neither generically conservative nor generically eager. It is:

- eager to honor an explicit durable correction;
- skeptical of inferred preference and ordinary work;
- strict about verified procedures;
- biased toward the artifact already in use;
- hostile to one-session skill proliferation; and
- incapable of turning any judgment into a durable write without the user-controlled path.

That is the useful part of Hermes's prompt design, transplanted into the stronger safety
architecture already present in this repository.
