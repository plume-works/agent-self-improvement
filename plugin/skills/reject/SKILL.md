---
name: reject
description: Reject a self-improve proposal the user has declined. Leaves the target file unchanged and remembers the fingerprint so the same lesson is not proposed again.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/si:*)
---

# Reject a proposal

Usage: `/self-improve:reject <proposal-id>`

Run exactly:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" reject-proposal --id <proposal-id>
```

The target file is not touched. The staged bytes are discarded; only the
proposal's fingerprint and a reason category are kept, so the same lesson is
suppressed if it comes up again.

Report the output verbatim. Do not argue for the proposal or re-propose a
variation of it in the same session.

If the user gave a reason worth categorizing, pass it:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" reject-proposal --id <proposal-id> --reason-category wrong_scope
```

Useful categories: `wrong_scope`, `wrong_owner`, `too_generic`, `already_known`,
`incorrect`, `declined`. Pass a category, never the user's own words.
