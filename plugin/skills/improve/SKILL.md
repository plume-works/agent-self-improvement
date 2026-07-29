---
name: improve
description: Review the current session for a reusable lesson and propose one exact durable change to a CLAUDE.md file, rule, or skill. Use when the user asks to remember an approach, when a correction should be retained, or when a self-improve candidate is available.
allowed-tools: Read, Grep, Glob, Bash(${CLAUDE_PLUGIN_ROOT}/scripts/si:*)
---

# Propose one durable lesson

You route an already-identified lesson to the artifact that should own it, then
stage one exact proposal for the user to approve.

**You never edit the destination file.** Staging goes through `si stage-proposal`,
which computes the hashes the user authorizes against. Editing a target directly
bypasses backup, verification, and rollback.

## 1. Get the candidate

If a candidate ID was supplied:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" show-candidate --id <candidate-id>
```

Otherwise list what is waiting:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" show-candidate
```

If there is no candidate and the user invoked this directly, identify the lesson
yourself from the current session. Hold to the same bar the reviewer uses: a
lesson is worth keeping only if it would have changed what you did earlier in
this session, it will still be true in three months, and you can name the
specific evidence for it. If nothing meets that bar, say so plainly and stop.
Proposing nothing is a good outcome.

## 2. Find the owner

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" find-owners --query "<owner_query from the candidate>"
```

This returns only paths the mutator will accept. Read the most promising ones
before choosing — ownership is a judgment about content, not filename.

Choose in this order, and stop at the first that fits:

1. **Patch the artifact already loaded** that covers this topic.
2. **Patch an existing umbrella** covering the class of thing the lesson is about.
3. **Add or patch a linked reference** owned by such an umbrella.
4. **Create a new skill** — only when no existing artifact plausibly owns it.

Creating a new file is the last resort, not the default. A pile of
single-purpose files is worse than a well-placed paragraph.

Scope: `project` when the lesson is true of this repository, `user` when it is
true of how this person works everywhere. Prefer `project` when torn.

## 3. Draft the exact bytes

Read the target in full. Write the complete new contents of the file, matching
its existing structure, heading style, and voice. Add the smallest thing that
carries the lesson — usually one bullet or one short paragraph.

Do not reformat unrelated lines, reorder sections, or fix unrelated problems you
notice. The diff the user reviews should contain only the lesson.

## 4. Stage it

Write the new contents to a temporary file, then:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" stage-proposal \
  --target "<absolute path>" \
  --candidate "<candidate-id>" \
  --reason "<one sentence on why this artifact owns the lesson>" \
  --content-file "<temp file>"
```

## 5. Present it

Show the command's output to the user **verbatim**, including the diff and the
two commands at the end. Do not summarize the diff, restate the hash, or
paraphrase the destination.

Then stop. The proposal is inert until the user types the apply command
themselves. Do not invoke `si apply-proposal` — an authorization exists only for
a command the user typed, so calling it yourself will simply fail.
