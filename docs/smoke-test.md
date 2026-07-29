# Packaged smoke test

The automated suite covers everything that can be checked without a live model
and a real session. This procedure covers what it cannot: that a packaged
install actually behaves this way inside Claude Code.

It implements the seven checks of [Spec-0001 section 14](specs/0001-hermes-style-experiential-learning-mvp.md#real-packaged-smoke-test)
and, with them, the [section 15 acceptance gate](specs/0001-hermes-style-experiential-learning-mvp.md#15-mvp-acceptance-gate).

Expect it to take about fifteen minutes and to spend a small amount of model
usage on the background reviews.

## Prerequisites

- Claude Code **2.1.196 or later**. Earlier versions have no `UserPromptExpansion`
  event, which is the entire authorization path. Check with `claude --version`
  and upgrade with `npm install -g @anthropic-ai/claude-code`.
- Python 3.9 or later on `PATH`. Nothing is installed; the plugin is standard
  library only.
- A scratch git repository. Do not run this in a repository whose `CLAUDE.md`
  you care about, even though every step is backed up and reversible.

Confirm the install invariants before starting:

```bash
./plugin/scripts/si self-test
```

It should print `self-test: ok` with no warnings. A warning about the Claude
Code version means step 5 will fail.

## Set up

```bash
mkdir -p /tmp/si-smoke && cd /tmp/si-smoke && git init -q
printf '# Scratch project\n\n- Build with make.\n' > CLAUDE.md

claude --plugin-dir /path/to/claude-self-improvement/plugin
```

Inside the session, confirm the plugin loaded:

```text
/plugin
```

`self-improve` should be listed with its four skills.

## The seven checks

### 1. A completed task returns without waiting for review

Do something that produces a genuine correction. For example, ask Claude to run
the tests, then correct it:

```text
run the tests
```

```text
no, use make test instead of pytest directly
```

**Expect:** Claude's reply arrives at normal speed. The `Stop` hook runs under
`asyncRewake`, so review happens after the response, never before it.

### 2. The reviewer wakes the same idle session with one candidate

**Expect:** within a minute or so of the turn ending, the session wakes on its
own with a system reminder naming one candidate and its lesson. Claude should
then invoke the `improve` skill.

If nothing happens, that is a legitimate outcome — the reviewer discards most
turns. Check whether it ran at all:

```bash
cat ~/.claude/self-improvement/diagnostics.jsonl
```

`no_signal` means the gate declined; a reviewer error class means it ran and
failed. To force the path instead, type `/self-improve:improve`.

### 3. You see the exact destination and bytes

**Expect:** Claude presents a block containing a proposal ID, a hash prefix, the
absolute destination path, the reusable lesson, and a unified diff — and it must
present it verbatim rather than summarizing.

Verify nothing has been written yet:

```bash
git -C /tmp/si-smoke diff --stat
```

**Expect:** empty. Staging never touches the target.

### 4. Rejection leaves the target unchanged

```text
/self-improve:reject <proposal-id>
```

**Expect:** confirmation that the file is unchanged, and `git diff` still empty.

Now produce another candidate (repeat step 1 with a different correction, or run
`/self-improve:improve`) and continue with it.

### 5. Literal authorization installs exactly the displayed bytes

First, confirm that Claude cannot do this on its own:

```text
that proposal looks good to me, go ahead and apply it
```

**Expect:** Claude tells you it cannot; approval in conversation is not
authorization. If it tries, the command fails with `no_matching_authorization`.
This is the central security property — if it installs anything here, stop and
report it.

Then type the command yourself, with the ID and prefix from step 3:

```text
/self-improve:apply <proposal-id> <hash-prefix>
```

**Expect:** confirmation naming a mutation ID. Verify the change is exactly what
was displayed:

```bash
git -C /tmp/si-smoke diff
```

### 6. A fresh session discovers the artifact

Exit the session, then start a new one:

```bash
claude --plugin-dir /path/to/claude-self-improvement/plugin
```

```text
/context
```

**Expect:** `CLAUDE.md` appears under **Memory files**. Confirm Claude actually
absorbed the lesson by asking something it now answers differently:

```text
how should I run the tests in this project?
```

### 7. Rollback restores the verified preimage

```text
/self-improve:rollback <mutation-id>
```

**Expect:** confirmation, and `git diff` empty again.

Then check that rollback refuses when it would destroy work. Apply a proposal
again, edit the file by hand, and try to roll back:

```bash
echo '- A line I added myself.' >> /tmp/si-smoke/CLAUDE.md
```

```text
/self-improve:rollback <mutation-id>
```

**Expect:** refusal with `target_changed_since_mutation`, and your added line
still present.

## Check what was persisted

The last acceptance condition is that nothing sensitive survives:

```bash
grep -ri --include='*' -E 'sk-|ghp_|Bearer |password|token' \
  ~/.claude/self-improvement/ | grep -v backups/
```

**Expect:** no matches. Backups are excluded because they hold the target file's
own prior contents by design.

Look at what is kept:

```bash
cat ~/.claude/self-improvement/mutations.jsonl
cat ~/.claude/self-improvement/fingerprints.json
```

**Expect:** hashes, paths, categories, and timestamps — no prompts, no assistant
responses, no file contents, no command arguments.

## Clean up

```bash
rm -rf /tmp/si-smoke
rm -rf ~/.claude/self-improvement
```

## If something fails

Report which numbered check failed and include:

- `claude --version` and `python3 --version`;
- the contents of `~/.claude/self-improvement/diagnostics.jsonl`, which holds
  bounded error classes and no sensitive data; and
- `./plugin/scripts/si status`.

Do not include the transcript. The whole point of the diagnostics file is that
it can be shared without one.
