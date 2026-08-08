#!/usr/bin/env bash
set -euo pipefail

workspace="${DEV_WORKSPACE_FOLDER:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

cd "$workspace"

# UV_PROJECT_ENVIRONMENT points at a named volume so the environment survives
# container rebuilds; .venv is a symlink to it for tooling that expects the
# conventional in-tree path.
if [ -e "$workspace/.venv" ]; then
    rm -rf "$workspace/.venv"
fi

uv sync --all-groups --all-extras

if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ]; then
    ln -s "$UV_PROJECT_ENVIRONMENT" "$workspace/.venv"
fi
