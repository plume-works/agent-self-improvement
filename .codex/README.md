# `.codex/` — Codex repository configuration

This repository consumes the shared `agentdev` catalog rather than publishing one, so this
directory holds only the Codex configuration the repository keeps for itself.

| Path                   | Purpose                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| `setup-codex-cloud.sh` | Codex Cloud bootstrap: ensures `gh` is present and authenticated. |

Inside the devcontainer, `.devcontainer/scripts/postCreateCommand.sh` installs the catalog
that the development image stages at `/opt/agentdev`, and
`.devcontainer/scripts/configure-codex.py` applies devcontainer-only sandbox and approval
policy. Neither needs anything checked in here.

`setup-codex-cloud.sh` is only useful on a Codex Cloud host that has no GitHub CLI; it is
harmless everywhere else.
