# `.claude/` — this repository's own Claude Code configuration

The plugin this repository develops lives in [`plugin/`](../plugin/) and is published through
[`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json). What remains in this
directory is the Claude Code configuration the repository keeps for itself.

| Path            | Purpose                                                                         |
| --------------- | ------------------------------------------------------------------------------- |
| `settings.json` | Extra known marketplaces and the third-party plugins enabled for this checkout. |

`settings.json` must be strict JSON: no comments and no trailing commas. Claude Code rejects
the file outright if it does not parse, which silently drops every permission and plugin
setting with it.

`settings.json` enables `agentdev@agent-devcontainer` from the
[`plume-works/agent-devcontainer`](https://github.com/plume-works/agent-devcontainer)
marketplace, which is what makes the `/agentdev:*` skills referenced in
[`AGENTS.md`](../AGENTS.md) available outside the devcontainer. Inside the devcontainer the
same catalog is installed by `.devcontainer/scripts/postCreateCommand.sh` from the copy the
development image stages at `/opt/agentdev`, so no additional declaration is required there.

`*.local.json` is gitignored, so `settings.local.json` can hold machine-specific permissions
without touching the shared configuration.
