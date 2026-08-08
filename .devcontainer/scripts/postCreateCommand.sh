#!/usr/bin/env bash
set -exuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace="${DEV_WORKSPACE_FOLDER:-$(cd "$script_dir/../.." && pwd)}"

# Named volumes are created root-owned by the daemon; make sure the container
# user owns the mount points it writes to.
sudo chown -R root:root \
    "$workspace/.cache" \
    /uv

# ~/.claude.json can't be backed directly by a named volume (Docker volumes are always
# directory-backed, so mounting one at a file path materializes an empty directory
# there instead of the file Claude Code expects). Persist it as a plain file inside the
# already-mounted agentdev-claude volume and symlink it into place instead.
claude_json_target="/root/.claude/claude.json"
if [[ -f /root/.claude.json && ! -L /root/.claude.json ]]; then
    mv /root/.claude.json "$claude_json_target"
elif [[ ! -e "$claude_json_target" ]]; then
    echo '{}' >"$claude_json_target"
fi
ln -sf "$claude_json_target" /root/.claude.json

# Sync the project environment into the container's .venv directory so that
# extension settings are valid when the container is rebuilt. This is a no-op if the environment is already up to date.
"$script_dir/uv-sync.sh"

# Install the catalog staged in the image. This has to happen here rather than
# during the image build: the persistent ~/.claude and ~/.codex volumes mount over
# where both agents record installed plugins, so a build-time install would be
# shadowed for every container whose volume already exists. At user scope for
# Claude, so it applies to every workspace opened in this container;
# postStartCommand.sh re-registers this checkout on top when there is one.
if [[ -n "${AGENTDEV_CATALOG_DIR:-}" && -d "$AGENTDEV_CATALOG_DIR" ]]; then
    "$script_dir/reinstall-agentdev-codex.sh" "$AGENTDEV_CATALOG_DIR"
    "$script_dir/reinstall-agentdev-claude.sh" "$AGENTDEV_CATALOG_DIR" user
else
    echo "No catalog staged in the image; skipping the image-scoped plugin install."
fi
