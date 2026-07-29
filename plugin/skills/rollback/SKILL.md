---
name: rollback
description: Undo a previously applied self-improve mutation, restoring the verified backup. Refuses if the file changed since.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/si:*)
---

# Roll back a mutation

Usage: `/self-improve:rollback <mutation-id>`

Run exactly:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" rollback-mutation --id <mutation-id>
```

The backup is restored only if the file still hashes to exactly what the
mutation installed. If it does not, the command refuses with
`target_changed_since_mutation`: someone edited the file after the mutation, and
restoring the backup would destroy that work.

When that happens, do not force it. Show the user the current file and the
mutation record, and let them decide what to keep.

Report the output verbatim.

To find a mutation ID, the apply command printed one, and the redacted journal
lists them:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" status
```
