#!/usr/bin/env bash
set -euo pipefail

# Register a catalog root as a Codex marketplace and install the plugin it
# publishes.
#
# Called twice with different roots. postCreate passes the catalog staged in the
# image, so any workspace gets the catalog. postStart passes nothing, which
# defaults to this checkout and re-registers the workspace copy on top — that is
# how the catalog is developed in place. Codex has no installation scopes.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

catalog_root="${1:-$(cd "$script_dir/../.." && pwd)}"

marketplace_json="$catalog_root/.agents/plugins/marketplace.json"

# Only the catalog's own repository ships a marketplace. Anywhere else this is a
# no-op, leaving whatever was installed from the image in place.
if [[ ! -f "$marketplace_json" ]]; then
  echo "$catalog_root declares no Codex marketplace; nothing to reinstall."
  exit 0
fi

marketplace_name="$(jq -er '.name' "$marketplace_json")"
plugin_name="$(jq -er '.plugins[0].name' "$marketplace_json")"

# Remove the marketplace declared by this root plus any marketplace still
# registered under an older name but pointing at the same root. Otherwise a
# marketplace rename can leave a stale plugin installation and cache behind.
mapfile -t stale_names < <(
  codex plugin marketplace list --json \
    | jq -r --arg root "$catalog_root" '
        .marketplaces[]
        | select(.root == $root or .marketplaceSource.source == $root)
        | .name
      '
)

while read -r name; do
  [[ -n "$name" ]] || continue
  codex plugin remove "$plugin_name@$name" || true
  codex plugin marketplace remove "$name" || true
done < <(printf '%s\n' "$marketplace_name" "${stale_names[@]}" | sort -u)

codex plugin marketplace add "$catalog_root"
codex plugin add "$plugin_name@$marketplace_name"
