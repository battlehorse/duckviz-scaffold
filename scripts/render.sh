#!/bin/sh
# Render sample apps from the working copy (every flag on; every flag off) with the local kit, and run their checks
# (ruff, pytest, the CLI, doctor).
# The scaffold's CI runs this; run it before a release. Usage: scripts/render.sh [output folder]
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/build}
rm -rf "$out" && mkdir -p "$out"

render() {
  name=$1; shift
  uvx copier copy --trust --defaults --quiet --vcs-ref HEAD "$root" "$out/$name" -d project_name="$name" -d description="Sample $name" \
    -d contract_name=sample -d kit_path="$root/kit" "$@"
  (cd "$out/$name" && git init -q -b main && uv sync -q && uv run ruff check . && uv run pytest -q \
    && uv run "$name" --help >/dev/null && uv run "$name" doctor)
  echo "✓ $name"
}

render all-on -d cloud_run=true -d demo_data=true -d config_style=toml \
  -d 'extra_apps=[{name: catalog, port: 8503, title: Catalog, hosted: false}]'
render all-off -d motherduck=false -d tailnet=false -d backup=false -d privacy_hook=false

# Not checked here: `docker build` of the all-on image. The samples use the local kit (kit_path), which is outside
# the image's build context; a released app fetches duckkit from GitHub instead. Build a real app's image to check it.
