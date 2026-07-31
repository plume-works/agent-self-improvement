---
name: apply
description: Apply a self-improve proposal the user has explicitly authorized by typing its ID and hash prefix. Only meaningful when the user types /self-improve:apply themselves.
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/si:*)
---

# Apply an authorized proposal

Usage: `/self-improve:apply <proposal-id> <hash-prefix>`

Authorization comes from the user typing that command, not from this skill being
invoked. If you reached this skill any other way — by deciding to call it, or
because the user said something that sounded like approval — there is no
authorization record and the command below will correctly refuse.

Run exactly:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/si" apply-proposal --id <proposal-id> --hash-prefix <hash-prefix>
```

Report the output verbatim.

If it fails, report the reason without retrying:

- `no_matching_authorization` — the command was not typed by the user, or the
  ten-minute window expired. Ask them to type it again.
- `stale_target` — the file changed since the proposal was staged. The proposal
  is void; offer to regenerate it with `/self-improve:improve`.
- `hash_mismatch` — the hash prefix does not match the proposal. Show them the
  correct one from `si show-proposal --id <proposal-id>`.
- `unreconciled_target` — an earlier mutation was interrupted and the file now
  holds unexpected content. Do not mutate anything; show the user the file and
  let them decide.

Never work around a failure by editing the file directly.
