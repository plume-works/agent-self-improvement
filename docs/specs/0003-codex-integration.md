# Spec-0003: Codex integration for experiential learning

- **Status:** Proposed; integration analysis only. **Evidence observed on 2026-08-01:** the current repository and Spec-0001 implementation were inspected; the current official Claude Code and Codex documentation was checked; `codex-cli 0.145.0` exposes plugin management and `codex exec`. **Evidence outstanding:** no Codex package, hook adapter, reviewer invocation, authorization flow, mutation, fresh-session discovery, or packaged smoke check has been implemented or observed.
- **Scope:** Standalone Codex CLI on one local user account. ChatGPT desktop, Codex IDE extension, Codex cloud, ChatGPT Work, and cross-machine learning are not certified by this specification.
- **Depends on:** [Spec-0001](0001-hermes-style-experiential-learning-mvp.md) for the learning, privacy, authorization, mutation, and rollback invariants.
- **Implementation strategy:** retain one host-neutral learning engine and add explicit Claude Code and Codex packaging, hook, reviewer, artifact-routing, and presentation adapters.

## 1. Goal

Bring the Spec-0001 experiential-learning loop to Codex without pretending that similarly named platform features have identical semantics.

The Codex integration must preserve these product properties:

1. deterministic event classification precedes model review;
2. review sees only bounded evidence from one completed turn;
3. the reviewer cannot mutate a durable artifact;
4. no durable change occurs without an exact, one-time user authorization;
5. the mutator applies only the reviewed bytes to an allowlisted target;
6. stale targets, path attacks, interruption, and verification failure do not overwrite unexpected content;
7. accepted changes are discoverable by a fresh Codex session; and
8. rollback restores a verified preimage.

Codex does not currently document an equivalent of Claude Code's asynchronous hook re-wake. The first Codex slice therefore uses a synchronous `Stop` continuation on signal-bearing turns. It is functional integration, not latency parity. Section 6 records the gap and the condition for removing it.

This specification does not change the accepted Claude Code MVP. Shared schemas or modules may be generalized only when the Claude acceptance evidence remains valid.

## 2. Verified platform baseline

This design relies on the following current, public platform contracts.

### 2.1 Claude Code baseline

- [Plugins](https://code.claude.com/docs/en/plugins) package skills, hooks, scripts, and other extensions under a `.claude-plugin/plugin.json` identity.
- [Hooks](https://code.claude.com/docs/en/hooks) expose `UserPromptSubmit`, `UserPromptExpansion`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SessionStart`, and `SessionEnd`.
- Claude's `asyncRewake` command-hook field runs a hook in the background and wakes an idle session when the hook exits with code 2.
- `UserPromptExpansion` reports a user-entered slash command, its arguments, expansion type, and command source. This is the current mutation-authorization seam.
- [Skills](https://code.claude.com/docs/en/slash-commands) are invoked with `/name`; plugin skills are namespaced as `/plugin:skill`.
- [Memory](https://code.claude.com/docs/en/memory) loads `CLAUDE.md`, `.claude/rules/*.md`, skills, and Claude-managed auto-memory through distinct mechanisms.

### 2.2 Codex baseline

- [Codex plugins](https://developers.openai.com/plugins/build/plugins) use `.codex-plugin/plugin.json` and can bundle skills and lifecycle hooks. Codex provides `PLUGIN_ROOT` and `PLUGIN_DATA` to plugin hook processes and also provides `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` there for compatibility.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks) include `UserPromptSubmit`, `PostToolUse`, `Stop`, `SessionStart`, and `SessionEnd`. They provide `session_id`, `turn_id`, `cwd`, `last_assistant_message`, and `stop_hook_active` where applicable.
- Codex documents that the `async` hook option is parsed but asynchronous command hooks are not yet supported. It does not document an `asyncRewake` equivalent.
- Codex does not document `UserPromptExpansion` or a distinct `PostToolUseFailure` event. `PostToolUse` does run for Bash commands that exit non-zero, with tool-specific data in `tool_response`.
- [Codex skills](https://learn.chatgpt.com/docs/build-skills) use the Agent Skills format, are explicitly invoked with `$name`, and may be packaged in plugins. Plugin skills are namespaced, for example `$self-improve:apply`.
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) is Codex's durable behavioral-instruction surface. Codex builds its chain once per run from `$CODEX_HOME/AGENTS.md` or `AGENTS.override.md`, then from the project root down to the launch directory.
- Codex's `.rules` files are command-execution policy, not a behavioral equivalent of Claude's Markdown `.claude/rules/*.md`.
- [Local memories](https://learn.chatgpt.com/docs/customization/memories) are generated state under `CODEX_HOME`; official guidance says not to rely on hand-editing them as the primary control surface.
- [`codex exec`](https://learn.chatgpt.com/docs/non-interactive-mode) supports saved authentication, ephemeral runs, output schemas, sandbox selection, model selection, and machine-readable output.
- Plugin availability is surface-specific. The [plugin guide](https://learn.chatgpt.com/docs/plugins) documents Codex CLI support and says plugins are not available in the IDE extension.

Current documentation is a design input, not acceptance evidence. Implementation must re-check these contracts and record the tested Codex version before relying on them.

## 3. Current Claude integration inventory

The current implementation is not merely “a plugin.” Its Claude dependencies occur at every layer below.

| Integration point | Current artifact | Claude-specific dependency |
| --- | --- | --- |
| Package identity | `plugin/.claude-plugin/plugin.json` | Claude manifest name and metadata |
| Marketplace | `.claude-plugin/marketplace.json` | Claude marketplace schema, install, cache, and refresh flow |
| Hook registration | `plugin/hooks/hooks.json` | Claude event names, `args`, matchers, `asyncRewake`, and `${CLAUDE_PLUGIN_ROOT}` |
| Persistent state root | `selfimprove/paths.py` | `CLAUDE_PLUGIN_DATA`, `CLAUDE_CONFIG_DIR`, and `~/.claude` fallback |
| Turn identity | `selfimprove/capture.py` | Claude `prompt_id`, with a rolling fallback |
| Prompt capture | `UserPromptSubmit` | Claude prompt event schema |
| Literal authorization | `UserPromptExpansion` | slash-command expansion, command source, name, and arguments |
| Failure capture | `PostToolUseFailure` | top-level `error`, `is_interrupt`, tool name, and tool input |
| Success capture | `PostToolUse` | Claude tool names and successful response semantics |
| Review trigger | `Stop` | `last_assistant_message`, `stop_hook_active`, background registries, and `asyncRewake` |
| Pending retrieval | `SessionStart` | startup context injection |
| Expiry sweep | `SessionEnd` | end-of-session cleanup opportunity |
| Reviewer | `selfimprove/reviewer.py` | `claude -p`, Claude model aliases, effort environment, tool disabling, hook disabling, and JSON output |
| Reviewer recursion | `SELF_IMPROVE_REVIEWER` | process environment passed to the nested Claude session |
| Candidate schema | `reviewer/schema.json` | `destination_kind` names `CLAUDE.md`, `rule`, and `skill` |
| Owner discovery | `selfimprove/owners.py` | Claude instruction, rule, and skill locations |
| Mutation allowlist | `selfimprove/allowlist.py` | `~/.claude` and `./.claude` layouts plus root `CLAUDE.md` |
| Manual workflows | `plugin/skills/*/SKILL.md` | slash-command syntax, `allowed-tools`, and `${CLAUDE_PLUGIN_ROOT}` in model-run Bash |
| Presentation | `selfimprove/commands.py` | `/self-improve:*` commands and wake-oriented follow-up wording |
| Smoke harness | `tests/smoke/` | `claude` CLI, Claude stream events, Claude auto-memory controls, and the pty wake |
| Build validation | `Makefile` | `claude plugin validate` and Claude-only live targets |

Every row needs either a Codex adapter or an explicit finding that the shared behavior is already portable. Merely adding `.codex-plugin/plugin.json` is insufficient.

## 4. Claude-to-Codex mapping

| Claude integration | Codex mapping | Parity | Required decision |
| --- | --- | --- | --- |
| `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | Direct | Ship both manifests, each pointing at its host-specific hooks and skills. |
| Claude marketplace | `.agents/plugins/marketplace.json` plus `codex plugin marketplace add` and `codex plugin add` | Adapted | Publish a Codex marketplace entry without replacing the Claude marketplace. |
| `${CLAUDE_PLUGIN_ROOT}` in hooks | `${PLUGIN_ROOT}` | Direct | Use native names in Codex hooks; compatibility variables are fallback only. |
| `${CLAUDE_PLUGIN_DATA}` | `${PLUGIN_DATA}` | Direct | Prefer the native Codex variable and keep host-local state by default. |
| `UserPromptSubmit.prompt_id` | `UserPromptSubmit.turn_id` | Direct after normalization | Normalize both to an internal `turn_id`. |
| `UserPromptSubmit.prompt` | `UserPromptSubmit.prompt` | Direct | Reuse marker detection after schema normalization. |
| `UserPromptExpansion` | exact full-prompt grammar in `UserPromptSubmit` | Partial | Authorize only a prompt consisting solely of one explicit `$self-improve:*` invocation and its required arguments. |
| `PostToolUseFailure` | `PostToolUse` plus tool-specific failure classifier | Partial | Initially certify only observed response shapes; never infer universal failure coverage. |
| `PostToolUse` | `PostToolUse` | Direct after tool-name normalization | Map `apply_patch` and aliases; omit unsupported hosted tools. |
| `Stop.last_assistant_message` | same field | Direct | Use the field; do not parse the unstable transcript format. |
| `Stop.stop_hook_active` | same field | Direct | Preserve the recursion guard. |
| `Stop.background_tasks` and `session_crons` | no documented Codex fields | Missing | Do not claim background-work-aware gating on Codex. |
| `asyncRewake` | synchronous `Stop` continuation | Missing latency parity | Run bounded review in the Stop hook only for a meaningful signal, then continue once when a candidate exists. |
| `SessionStart` context | `SessionStart` developer context | Direct | Surface pending candidates through bounded `additionalContext`. |
| immediate `SessionEnd` cleanup | advisory Codex `SessionEnd`, possibly delayed | Partial | Delete turn data at review completion; use SessionEnd only for expiry sweeping. |
| `claude -p` reviewer | `codex exec --ephemeral --output-schema` | Adapted | Use a dedicated restrictive permission profile, clean environment, isolated cwd, hooks off, memories off, and no network. |
| Claude model alias and effort env | Codex model and `model_reasoning_effort` config | Adapted | Give Codex separate defaults; preserve user overrides. |
| `CLAUDE.md` | `AGENTS.md` | Direct in purpose | Use only files Codex actually discovers for the relevant fresh session. |
| `.claude/rules/*.md` | no general equivalent | Missing | Route short standing behavior to a loaded `AGENTS.md`; route procedures to a skill; discard when file-path scoping is essential. |
| `.claude/skills` | `.agents/skills` | Direct in purpose | Use Codex's documented repository and user locations. |
| Claude auto-memory | Codex local memories | Direct policy | Treat as generated, read-only state; never target it for mutation. |
| `/self-improve:skill` | `$self-improve:skill` | Adapted | Provide Codex-specific skill bodies and examples. |
| `allowed-tools` frontmatter | Codex sandbox, approvals, hooks, and optional `agents/openai.yaml` policy | Not equivalent | Do not claim that Claude frontmatter constrains Codex tools. |
| Claude fresh-session smoke | fresh Codex CLI process | Direct in intent | Verify the target is loaded in a new process, not merely written. |
| pty async-wake smoke | synchronous continuation smoke | Different | Test the supported Codex continuation and keep idle wake as an outstanding capability gap. |

## 5. Package and adapter architecture

The package should become dual-host without forking the learning engine.

```text
plugin/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── hooks/
│   ├── claude.json
│   └── codex.json
├── skills/
│   ├── claude/
│   │   ├── improve/SKILL.md
│   │   ├── apply/SKILL.md
│   │   ├── reject/SKILL.md
│   │   └── rollback/SKILL.md
│   └── codex/
│       ├── improve/SKILL.md
│       ├── apply/SKILL.md
│       ├── reject/SKILL.md
│       └── rollback/SKILL.md
├── scripts/
│   └── si
├── reviewer/
│   ├── prompt.md
│   └── schema.json
└── selfimprove/
    ├── hosts/
    │   ├── claude.py
    │   └── codex.py
    └── ... shared engine modules
```

Each manifest must explicitly select its host hook file and skill directory. Default discovery must not expose the other host's skill bodies.

The internal host adapter owns:

- event normalization;
- plugin root and data root resolution;
- reviewer command construction and response parsing;
- host-specific durable-artifact discovery;
- host-specific invocation syntax and presentation; and
- capabilities reported by `si self-test`.

Capture, gating, redaction, schemas, proposal hashing, authorization consumption, atomic mutation, journaling, and rollback remain shared unless a host contract forces a difference.

Every turn, candidate, proposal, authorization, diagnostic, and mutation record must include `host: "claude" | "codex"`. State is host-local by default. An explicitly shared `SELF_IMPROVE_STATE_DIR` must still partition transient state by host so equal session or turn identifiers cannot collide.

## 6. Documented parity gaps

### GAP-1: no asynchronous idle-session wake

Codex currently documents that asynchronous command hooks are unsupported. A `Stop` hook can synchronously continue the agent by returning a block/continuation result, but a completed background process has no documented callback that reactivates the same idle CLI session.

The Codex MVP must therefore:

1. run the cheap gate in `Stop`;
2. exit immediately for no-signal turns;
3. run a bounded synchronous review for a signal-bearing turn;
4. exit silently for discard or failure; and
5. return one continuation with a candidate identifier when review proposes.

This can delay completion of a signal-bearing turn by the reviewer timeout. Documentation and status output must say so. The implementation must not describe this as asynchronous or as a wake.

Do not emulate a wake with an undocumented detached process, by editing Codex session files, or by starting an unrelated app-server instance. This gap closes only when an official same-session asynchronous hook/callback is documented and observed in a packaged test.

### GAP-2: no command-expansion provenance event

Codex does not document a `UserPromptExpansion` event carrying a parsed skill name, arguments, and source. `UserPromptSubmit` does provide the raw prompt before the model runs.

For Codex, an authorization may be minted only when the complete trimmed prompt matches one canonical grammar:

```text
$self-improve:apply <proposal-id> <hash-prefix>
$self-improve:reject <proposal-id>
$self-improve:rollback <mutation-id>
```

No prefix, suffix, quote, code fence, prose, multiple command, or embedded example is accepted. The parser must bind the authorization to `session_id`, `turn_id`, operation, object ID, and hash prefix where applicable. A model-authored shell call does not create a `UserPromptSubmit` event and cannot mint the record.

This proves a host-supplied user prompt, not a physical keystroke. App-server clients and terminal automation able to submit user turns remain inside the user-input trust boundary, just as terminal control is inside the Claude boundary. The product must describe the boundary accurately.

The first packaged test must observe the exact prompt delivered when a user invokes a namespaced plugin skill. Until then, authorization is designed but unverified.

### GAP-3: no distinct tool-failure event

Codex combines successful and non-zero Bash completion under `PostToolUse`; other tool results are tool-specific. There is no documented generic `error` field equivalent to Claude's `PostToolUseFailure`.

The Codex adapter must use an allowlist of observed, fixture-backed classifiers. The first slice should support:

- Bash/unified-exec completion when the documented or observed response includes an unambiguous non-zero exit status;
- a later compatible zero exit for failure-to-success pairing; and
- user interruption only when an explicit, observed field distinguishes it.

Unknown response shapes are ignored, not guessed. MCP errors, `apply_patch` failures, hosted tools, and local function tools remain uncertified until their hook payloads are captured in redacted fixtures and tested.

### GAP-4: no documented `codex exec` “no tools at all” switch

The current Claude reviewer removes every tool. `codex exec` documents output schemas and sandboxing but no general CLI flag that removes Bash and file tools.

The Codex replacement is a restrictive reviewer permission profile that:

- denies filesystem reads by default, granting only minimal runtime paths needed to execute tools;
- grants no project, user-home, plugin-data, or transcript read access to model-run commands;
- grants no filesystem writes;
- grants no network access;
- forwards no ambient environment variables to model-run commands;
- disables web search, MCP servers, plugins, skills, hooks, subagents, and memories where the public configuration surface permits;
- runs from a private empty directory outside the target project; and
- receives the reviewer prompt and evidence through the Codex request, not through readable project files.

The property to prove is stronger than “the prompt says not to use tools”: a reviewer attempt to read the project, user home, plugin state, or environment and an attempt to write must fail in acceptance tests.

If the installed Codex version cannot enforce that profile for a nested `codex exec`, the local-auth reviewer path is blocked. The only acceptable fallback is an explicit, separately specified OpenAI API reviewer with no tools and its own credential contract; it must not silently broaden access.

### GAP-5: no behavioral equivalent of `.claude/rules/*.md`

Codex `.rules` files enforce command policy and must never receive model-authored behavioral prose. Codex also discovers nested `AGENTS.md` only along the project-root-to-launch-directory chain once per run; it does not document Claude-style lazy path-glob rules.

The router must therefore:

- use the active `AGENTS.md` chain for short standing behavior;
- use a skill for a reusable multi-step procedure;
- patch an existing loaded nested `AGENTS.md` only when it already owns the topic;
- never create `AGENTS.override.md` automatically, because it replaces rather than augments `AGENTS.md` at that directory level; and
- discard a candidate whose correctness depends on file-glob activation that Codex cannot represent.

### GAP-6: surface coverage

This specification certifies Codex CLI only. It does not infer that the CLI, desktop host, IDE extension, cloud environment, or ChatGPT Work share a filesystem, plugin cache, hook process, authentication state, or local memories. The current plugin documentation says the IDE extension does not support plugins, so IDE certification is not merely untested; it is outside the documented plugin surface.

## 7. Codex hook design

The Codex hook file registers only supported events.

### 7.1 `UserPromptSubmit`

One bounded handler performs two independent operations:

1. capture correction and retention markers using `session_id` plus `turn_id`; and
2. parse exact authorization prompts from section 6.

The prompt is stored ephemerally only when Spec-0001 permits it. Authorization parsing records IDs and a hash prefix, never the surrounding prompt.

Codex ignores matchers for this event, so selection occurs in the script.

### 7.2 `PostToolUse`

Register a narrow matcher for certified tool paths. The adapter converts the host payload into one of:

```json
{"outcome":"failure","tool":"Bash","signature":"...","error_class":"nonzero_exit"}
```

```json
{"outcome":"success","tool":"Bash","signature":"..."}
```

Only normalized records reach the shared capture module. Raw `tool_input` and `tool_response` are not persisted.

### 7.3 `Stop`

The handler:

1. exits for `stop_hook_active`, reviewer-originated work, plugin-generated continuations, disabled state, or an already-reviewed turn;
2. loads the turn by `session_id` and `turn_id`;
3. runs the deterministic gate;
4. deletes no-signal turn data and exits;
5. invokes the isolated Codex reviewer synchronously within the configured timeout;
6. deletes the ephemeral turn for discard or failure and exits;
7. stores one candidate; and
8. returns one bounded continuation telling Codex that candidate `<id>` is ready for the improve workflow.

The continuation must contain no proposal bytes and no user authorization text. The next `Stop` observes `stop_hook_active` and exits. A hard internal counter must also prevent more than one plugin continuation for a turn even if a host version reports the flag incorrectly.

### 7.4 `SessionStart`

On `startup`, `resume`, `clear`, or `compact`, surface unexpired pending candidates as bounded developer context. Do not review, mutate, or inject proposal bytes.

This is recovery for candidates stored before a continuation failure; it is not a substitute for idle wake.

### 7.5 `SessionEnd`

Run only the expiry sweep within Codex's documented maximum timeout. Because Codex may delay this event until a conversation has been idle and closed, correctness must not depend on it.

## 8. Reviewer integration

The reviewer remains an independent model call. Its transport changes from `claude -p` to `codex exec`.

The normative invocation must provide the equivalent of:

```text
codex exec
  --ephemeral
  --ignore-user-config
  --ignore-rules
  --skip-git-repo-check
  --output-schema <plugin>/reviewer/schema.json
  --model <configured reviewer model>
  --cd <private empty reviewer cwd>
  -c features.hooks=false
  -c features.memories=false
  -c agents.enabled=false
  -c web_search="disabled"
  -c shell_environment_policy.inherit="none"
  -c default_permissions="self-improve-reviewer"
  -c model_reasoning_effort=<configured effort>
```

The exact argument vector depends on the tested Codex configuration schema. It must be constructed as an argument list, not a shell string. Tests must assert the effective permission profile and negative read/write/network probes, not only the presence of flags.

`SELF_IMPROVE_REVIEW_PROVIDER` selects `claude` or `codex`; provider-specific model defaults and effort settings must not share one ambiguous value. The existing fake reviewer remains the deterministic test transport.

Reviewer output should migrate from host filenames to host-neutral destinations:

```json
{
  "destination_kind": "instruction | scoped_instruction | skill",
  "destination_scope": "project | user"
}
```

The host adapter translates that intent to a concrete, allowlisted artifact. During migration, the Claude adapter may translate the old `CLAUDE.md | rule | skill` enum, but persisted records must carry a schema version and host so old and new meanings cannot be confused.

## 9. Codex routing and mutation allowlist

The Codex mutator may target only the shapes below.

| Scope | Allowed target | Creation policy |
| --- | --- | --- |
| User instruction | `$CODEX_HOME/AGENTS.md` | May create after exact review and approval |
| Project instruction | `<project-root>/AGENTS.md` | May create after exact review and approval |
| Existing loaded instruction | an `AGENTS.md` on the current root-to-cwd chain | Patch only; do not create a nested file merely to simulate path rules |
| Existing loaded override | an `AGENTS.override.md` on that same chain | Patch only when it is already the owner; never create automatically |
| User skill | `$HOME/.agents/skills/<name>/SKILL.md` | May create only when no existing owner fits |
| Project skill | `<repo-root>/.agents/skills/<name>/SKILL.md` | May create only when no existing owner fits |

The path resolver must compute `$CODEX_HOME`, home, project root, cwd, and the active instruction chain separately. It must not derive Codex paths from `~/.claude`, or assume that a custom `CODEX_HOME` also relocates `$HOME/.agents/skills`.

The following remain forbidden:

- `$CODEX_HOME/config.toml` and project `.codex/config.toml`;
- `hooks.json` and inline hook configuration;
- Codex `.rules` command-policy files;
- local memory files;
- installed plugin caches and bundled plugin skills;
- authentication, session, transcript, log, SQLite, and marketplace state;
- `AGENTS.override.md` creation; and
- arbitrary project source files.

Existing symlink, containment, preimage-hash, atomic-write, backup, verification, reconciliation, and rollback rules remain normative.

Owner discovery must search before creating. It may read only bounded metadata and reviewed artifact contents, and it must record which instruction files were actually in the active Codex chain. A filename's existence does not prove that Codex loaded it.

## 10. Codex skills and approval presentation

Codex gets host-specific skill bodies because invocation, path resolution, and tool-permission semantics differ.

- `$self-improve:improve [focus]` retrieves or forces one review and stages one exact proposal.
- `$self-improve:apply <proposal-id> <hash-prefix>` consumes the authorization minted from that exact user prompt.
- `$self-improve:reject <proposal-id>` rejects without touching the target.
- `$self-improve:rollback <mutation-id>` restores a verified backup.

The apply, reject, and rollback skills must set `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. This is defense in depth, not the authorization boundary.

Codex documentation guarantees plugin root/data variables to hook processes, not to arbitrary Bash calls the model writes while following a skill. Codex skill instructions must therefore resolve helper scripts relative to the selected `SKILL.md` location, or use another documented plugin resource mechanism observed in a packaged test. They must not assume `${CLAUDE_PLUGIN_ROOT}` is present in model-run commands.

Claude's `allowed-tools` frontmatter must not appear in the Codex security argument. Codex sandbox and approval policy govern tool execution. A skill calling the dispatcher may prompt for permission; the flow must remain correct if permission is denied.

Presentation retains Spec-0001's invariant: show the exact destination, diff, proposal ID, and hash prefix; stop; require the user to submit the canonical apply invocation in a new prompt.

## 11. State, privacy, and memory

Spec-0001's state lifetimes and prohibited data apply unchanged.

Codex-specific additions are:

- prefer `PLUGIN_DATA` in hook processes;
- fall back to `$CODEX_HOME/self-improvement/` only for direct/manual dispatcher use;
- never infer that Claude and Codex plugin-data directories are shared;
- include host and normalized turn ID in every record;
- do not parse Codex transcripts, whose hook documentation says the format is not stable;
- disable Codex memory generation for the reviewer; and
- treat Codex local memories as read-only generated state.

The plugin may inspect allowlisted `AGENTS.md` and `SKILL.md` owners. It must not inspect Codex memory bodies to deduplicate a lesson until OpenAI documents a stable read contract appropriate for third-party mutation workflows. Until then, memory coexistence is tested behaviorally: the plugin must neither target nor corrupt memory, and a fresh-session instruction check must distinguish an applied artifact from memory recall.

## 12. Required implementation changes

| Area | Required change |
| --- | --- |
| Manifests | add `.codex-plugin/plugin.json`; make both manifests select host-specific hooks and skills |
| Marketplace | add `.agents/plugins/marketplace.json` without changing the Claude listing |
| Hooks | split Claude and Codex registrations; remove unsupported Codex events and fields |
| Host detection | add explicit provider/host adapter; prefer `PLUGIN_*` on Codex |
| Capture | normalize `prompt_id`/`turn_id`; add result classifiers for Codex `PostToolUse` |
| Authorization | add exact full-prompt parser for Codex `UserPromptSubmit` |
| Orchestration | add Codex synchronous continuation path; retain Claude `asyncRewake` path |
| Reviewer | add `codex exec` transport, schema-output parsing, restrictive profile, and probes |
| Schema | version and generalize destination kinds |
| Owners/allowlist | add AGENTS chain and `.agents/skills`; keep Claude roots separate |
| Skills | add Codex invocation text, path resolution, and implicit-invocation metadata |
| Presentation | emit host-native `$self-improve:*` commands |
| Self-test | report host, manifest, hook capability, reviewer CLI/version, state root, and unsupported parity features |
| Fixtures | add redacted Codex payloads observed from the target CLI version |
| Smoke tests | add independent Codex package, continuation, authorization, fresh-session, and rollback checks |
| Documentation | describe supported hosts and their non-equivalent latency and event coverage |

## 13. Test requirements

### 13.1 Deterministic tests

- Claude and Codex payloads normalize to the same internal event schema.
- Session and turn identifiers do not collide across hosts.
- Exact Codex apply/reject/rollback prompts authorize; embedded, quoted, suffixed, prefixed, malformed, and model-run lookalikes do not.
- Unknown Codex tool results are ignored.
- Each certified non-zero result creates one failure and a compatible zero result resolves it.
- Codex target discovery includes only the active AGENTS chain and documented skill roots.
- `.codex/config.toml`, hooks, `.rules`, memories, plugin caches, transcripts, and arbitrary files are rejected.
- Codex reviewer arguments disable hooks, memories, network, web search, and subagents and select the restrictive profile.
- Reviewer probes cannot read the repository, home, plugin data, environment secrets, or write a file.
- `stop_hook_active` and the internal continuation counter prevent recursion.
- Existing Claude tests continue to pass after shared-schema changes.

### 13.2 Integration tests

- Redacted fixtures for every supported Codex hook event and every certified tool-response shape.
- Fake reviewer outcomes: discard, propose, malformed, timeout, provider failure, and permission-profile failure.
- A valid candidate produces exactly one Codex Stop continuation.
- No signal, discard, malformed output, timeout, and duplicate candidate produce no continuation.
- A pending candidate is added as bounded SessionStart context.
- Literal Codex user authorization applies exactly the staged bytes; conversational approval and implicit skill selection do not.
- Stale target, symlink, traversal, and changed-since-mutation rollback all refuse safely.

### 13.3 Packaged Codex CLI smoke test

Against one recorded Codex CLI version:

1. add the repository's Codex marketplace and install the plugin;
2. review and trust its exact hook definitions;
3. start a fresh Codex CLI session with isolated `CODEX_HOME`, project, and plugin state;
4. observe `UserPromptSubmit`, `PostToolUse`, `Stop`, `SessionStart`, and `SessionEnd` payloads used by the adapter;
5. complete a correction-bearing turn and observe one synchronous candidate continuation;
6. observe an ordinary no-signal turn remain silent and avoid a reviewer call;
7. reject one proposal and verify the target hash is unchanged;
8. submit the exact `$self-improve:apply` prompt and verify only the displayed bytes are installed;
9. launch a fresh process with memories disabled and observe the applied AGENTS instruction or skill;
10. roll back and verify the preimage hash; and
11. inspect persisted state for forbidden prompt, assistant, transcript, tool-output, credential, and environment bodies.

The test must separately report unsupported async wake and uncertified tool-failure categories. A passing synchronous continuation must not be presented as wake evidence.

## 14. Implementation sequence

### Slice C1: dual package and manual lifecycle

- Add the Codex manifest, marketplace, native skills, path adapter, and self-test.
- Stage, authorize, apply, discover in a fresh Codex process, and roll back one proposal without automatic review.
- Preserve the Claude package and offline evidence.

### Slice C2: Codex event capture

- Capture and commit redacted real hook fixtures.
- Add prompt/turn normalization and the narrow PostToolUse result classifier.
- Keep automatic model review disabled.

### Slice C3: isolated Codex reviewer

- Prove the restrictive permission profile with negative read/write/network/environment tests.
- Add the `codex exec` transport and structured-output validation.
- Verify recursion, timeout, provider-failure, quota, and malformed-output behavior.

### Slice C4: Stop continuation

- Enable synchronous review only after the deterministic gate.
- Continue once for a valid candidate and remain silent otherwise.
- Measure and document signal-turn latency.

### Slice C5: packaged acceptance

- Install through the Codex marketplace path.
- Run the full Codex smoke test.
- Update support status only for evidence observed in that run.

Each slice is committed as a checkpoint after its own evidence is observed. A later Codex failure does not invalidate the already completed user task or the Claude Code implementation.

## 15. Acceptance gate

The Codex integration may be called implemented only after a packaged local workflow proves all of the following:

1. the installed Codex package loads its native skills and trusted hooks;
2. automatic reflection is gated by supported meaningful signals;
3. no-lesson turns remain silent and produce no proposal;
4. the reviewer cannot read unrelated local state, access the network or environment, or mutate files;
5. the direct user-prompt authorization cannot be minted by model action or conversational approval;
6. owner search prefers a loaded AGENTS artifact or existing skill before creation;
7. approval applies exactly reviewed bytes to one Codex-allowlisted target;
8. stale edits, path attacks, interruption, and ambiguous installation fail without overwriting unexpected content;
9. a fresh Codex process discovers the applied instruction or skill with memories disabled;
10. verified rollback restores the preimage;
11. persisted state contains no forbidden prompt, assistant, transcript, credential, environment, or raw tool-output body; and
12. status and documentation call the review path synchronous and list unsupported idle wake and tool-failure coverage accurately.

The accepted claim will be narrow: Codex CLI can notice a supported meaningful experience at the end of a turn, review it under a restrictive local boundary, and propose one user-authorized durable instruction or skill. It will not claim asynchronous idle wake, universal tool-failure observation, IDE support, cloud support, cross-host state sharing, or autonomous memory editing.
